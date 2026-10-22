"""Pack an accepted folder build with Velopack and publish it to GitHub and CNB.

Without --upload the script stops after packing, so the feed and packages can be tried
against a local folder first. Uploading needs `gh` signed in, a `cnb` git remote and CNB_TOKEN.
--cnb-only finishes an interrupted CNB upload from the packages already in --releases-dir.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from aram_demo import __version__
from aram_demo.updater import CNB_FEED_TAG, CNB_REPO, FEEDS, GITHUB_REPO, PACK_ID
from scripts.package_binary import package, sha

CNB_API = 'https://api.cnb.cool'
CHANNEL = 'win'
FEED = f'releases.{CHANNEL}.json'
# Velopack names the installers after the pack id; releases publish them under neutral names.
# Packages keep the pack id: installed copies find their updates by it.
INSTALLERS = {f'{PACK_ID}-{CHANNEL}-Setup.exe': 'HexCompanion-Windows-x64-Setup.exe',
              f'{PACK_ID}-{CHANNEL}-Portable.zip': 'HexCompanion-Windows-x64.zip'}
GITHUB_FEED = dict(FEEDS)['GitHub']
UPLOAD_ATTEMPTS = 3
FEED_RELEASE_NOTES = '程序自动更新从这里读取更新源与安装包。每次发版都会替换其中的文件，请勿删除。'


def version_key(version):
    return tuple(int(part) for part in version.split('.'))


def run(*command, cwd=ROOT, check=True):
    return subprocess.run([str(part) for part in command], cwd=cwd, check=check, capture_output=True, text=True,
                          encoding='utf-8', errors='replace')


def git(*args):
    return run('git', *args).stdout.strip()


def read_feed(releases):
    path = releases / FEED
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {'Assets': []}


def pack(app_dir, releases, version, notes):
    releases.mkdir(parents=True, exist_ok=True)
    packed = [asset for asset in read_feed(releases)['Assets'] if asset['Type'] == 'Full' and asset['Version'] == version]
    if packed:
        # Packing first and uploading later is the documented flow; reuse packages of this very build.
        with zipfile.ZipFile(releases / packed[0]['FileName']) as package:
            inside = hashlib.sha256(package.read('lib/app/HexCompanion.exe')).hexdigest()
        if inside != sha(app_dir / 'HexCompanion.exe'):
            raise SystemExit(f'{version} 已用另一份构建打包。请提升版本号，或删除 {releases} 中 {version} 的包和更新源条目。')
        print(f'{version} 已用这份构建打包，沿用现有包')
        return
    older = [asset for asset in read_feed(releases)['Assets'] if asset['Type'] == 'Full'
             and version_key(asset['Version']) < version_key(version) and (releases / asset['FileName']).is_file()]
    if not older:
        # A delta needs the previous full package; take it from the published GitHub feed.
        result = run('vpk', 'download', 'http', '--url', GITHUB_FEED, '-o', releases, '-c', CHANNEL, check=False)
        print('已取回上一版完整包' if result.returncode == 0 else '没有已发布的更新源，本次只生成完整包')
    result = run('vpk', 'pack', '-u', PACK_ID, '-v', version, '-p', app_dir, '-e', 'HexCompanion.exe',
                 '--packTitle', '海克斯随行', '--packAuthors', GITHUB_REPO.split('/')[0],
                 '-i', ROOT / 'packaging/hex-companion.ico', '--releaseNotes', notes,
                 '-o', releases, '-c', CHANNEL, check=False)
    if result.returncode:
        raise SystemExit('vpk pack 失败：\n' + result.stdout[-3000:] + result.stderr[-3000:])


def stage(releases, version, keep_deltas):
    """Returns (packages, installers, feed). The feed lists only the packages uploaded beside it:
    this full package and recent deltas."""
    feed = read_feed(releases)
    full = [asset for asset in feed['Assets'] if asset['Type'] == 'Full' and asset['Version'] == version]
    assert len(full) == 1, f'{FEED} 中缺少 {version} 的完整包'
    deltas = sorted((asset for asset in feed['Assets'] if asset['Type'] == 'Delta'
                     and version_key(asset['Version']) <= version_key(version)
                     and (releases / asset['FileName']).is_file()),
                    key=lambda asset: version_key(asset['Version']), reverse=True)[:keep_deltas]
    staged = releases / f'upload-{version}'
    staged.mkdir(exist_ok=True)
    feed_path = staged / FEED
    feed_path.write_text(json.dumps({**feed, 'Assets': full + deltas}, ensure_ascii=False, indent=2), encoding='utf-8')
    packages = [releases / asset['FileName'] for asset in full + deltas]
    missing = [path.name for path in packages + [releases / name for name in INSTALLERS] if not path.is_file()]
    assert not missing, f'缺少待上传文件：{missing}'
    for asset in full + deltas:
        assert sha(releases / asset['FileName']) == asset['SHA256'].lower(), f'校验不符：{asset["FileName"]}'
    installers = [staged / published for published in INSTALLERS.values()]
    for built, target in zip(INSTALLERS, installers):
        shutil.copyfile(releases / built, target)
    return packages, installers, feed_path


def prepare_tag(tag):
    """Releases come from a pushed main; the tag is created here and pushed to both hosts."""
    if git('rev-parse', '--abbrev-ref', 'HEAD') != 'main':
        raise SystemExit('请在 main 分支发布。')
    if git('status', '--porcelain', '--untracked-files=no'):
        raise SystemExit('工作区有未提交的修改，发布前先提交。')
    git('fetch', 'origin', 'main')
    head = git('rev-parse', 'HEAD')
    if git('rev-parse', 'origin/main') != head:
        raise SystemExit('本地 main 与 origin/main 不一致，先推送或拉取。')
    if run('git', 'remote', 'get-url', 'cnb', check=False).returncode:
        raise SystemExit(f'缺少 cnb 远程仓库：git remote add cnb https://cnb.cool/{CNB_REPO}.git')
    existing = run('git', 'rev-parse', '--verify', '--quiet', f'refs/tags/{tag}^{{commit}}', check=False).stdout.strip()
    if existing and existing != head:
        raise SystemExit(f'标签 {tag} 已指向其他提交 {existing[:12]}。')
    if not existing:
        git('tag', tag)
    git('push', 'origin', f'refs/tags/{tag}')
    git('push', 'cnb', 'main', f'refs/tags/{tag}')


def prepare_feed_tag(tag):
    """The CNB feed release needs its tag once. The tag then stays on the commit it was made for."""
    run('git', 'fetch', 'cnb', f'refs/tags/{CNB_FEED_TAG}:refs/tags/{CNB_FEED_TAG}', check=False)
    if run('git', 'rev-parse', '--verify', '--quiet', f'refs/tags/{CNB_FEED_TAG}', check=False).returncode:
        git('tag', CNB_FEED_TAG, f'{tag}^{{commit}}')
    git('push', 'cnb', f'refs/tags/{CNB_FEED_TAG}')


def publish_github(tag, title, notes, files, feed_path):
    repo = ['-R', GITHUB_REPO]
    if run('gh', 'release', 'view', tag, *repo, check=False).returncode:
        run('gh', 'release', 'create', tag, *repo, '--draft', '--verify-tag', '--title', title, '--notes-file', notes)
    run('gh', 'release', 'upload', tag, *repo, '--clobber', *files)
    # The feed goes last, so a client never reads a feed whose packages are still uploading.
    run('gh', 'release', 'upload', tag, *repo, '--clobber', feed_path)
    run('gh', 'release', 'edit', tag, *repo, '--draft=false', '--prerelease=false', '--latest')
    print('GitHub Release 已发布')


class CNB:
    def __init__(self, token):
        self.token = token
        self.base = f'{CNB_API}/{CNB_REPO}/-/releases'

    def request(self, method, url, payload=None, missing_ok=False, optional=False):
        request = urllib.request.Request(url, method=method, data=None if payload is None else json.dumps(payload).encode(),
                                         headers={'Accept': 'application/vnd.cnb.api+json',
                                                  'Authorization': f'Bearer {self.token}',
                                                  'Content-Type': 'application/json',
                                                  'User-Agent': 'HexCompanion-Release'})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            if missing_ok and exc.code == 404:
                return None
            if optional:
                print(f'CNB {method} {url} 返回 {exc.code}，已跳过')
                return None
            raise SystemExit(f'CNB {method} {url} 返回 {exc.code}：{exc.read()[:500].decode(errors="replace")}')
        return json.loads(body) if body else {}

    def release(self, tag, name, body):
        """The release for tag, created as a draft when missing."""
        release = self.request('GET', f'{self.base}/tags/{urllib.parse.quote(tag, safe="")}', missing_ok=True)
        if release is None:
            release = self.request('POST', self.base, {'tag_name': tag, 'name': name, 'body': body, 'draft': True,
                                                       'prerelease': False, 'make_latest': 'false',
                                                       'target_commitish': 'main'})
        return release

    def upload(self, release, path, replace=False):
        """Skips a file already there at full size, so a rerun resumes an interrupted publish."""
        size = path.stat().st_size
        if not replace and any(asset.get('name') == path.name and asset.get('size') == size
                               for asset in release.get('assets') or ()):
            print(f'CNB 已有附件：{path.name}')
            return
        for attempt in range(1, UPLOAD_ATTEMPTS + 1):
            try:
                self.put(release['id'], path, size)
                break
            except OSError as exc:
                if attempt == UPLOAD_ATTEMPTS:
                    raise SystemExit(f'CNB 附件 {path.name} 上传失败：{exc}')
                print(f'CNB 附件 {path.name} 上传中断（{exc}），第 {attempt + 1} 次重试')
        print(f'已上传 CNB 附件：{path.name}')

    def put(self, release_id, path, size):
        info = self.request('POST', f'{self.base}/{release_id}/asset-upload-url',
                            {'asset_name': path.name, 'overwrite': True, 'size': size})
        with path.open('rb') as stream:
            request = urllib.request.Request(info['upload_url'], data=stream, method='PUT',
                                             headers={'Authorization': f'Bearer {self.token}',
                                                      'Content-Length': str(size)})
            with urllib.request.urlopen(request, timeout=600) as response:
                response.read()
        if info.get('verify_url'):
            self.request('POST', info['verify_url'])

    def publish(self, tag, title, body, packages, installers, feed_path):
        """Packages and the feed go to the fixed feed release the app reads; installers to the version's release."""
        feed = self.release(CNB_FEED_TAG, '自动更新源', FEED_RELEASE_NOTES)
        for path in packages:
            self.upload(feed, path)
        # The feed goes last, so a client never reads a feed whose packages are still uploading.
        self.upload(feed, feed_path, replace=True)
        # A prerelease, so the version's release stays the latest one on the releases page.
        self.request('PATCH', f'{self.base}/{feed["id"]}', {'name': '自动更新源', 'body': FEED_RELEASE_NOTES,
                                                             'draft': False, 'prerelease': True, 'make_latest': 'false'})
        keep = {path.name for path in (*packages, feed_path)}
        for asset in feed.get('assets') or ():
            if asset.get('name') not in keep and asset.get('id'):
                # Old packages only take space once the new feed is up; a failed delete is not fatal.
                self.request('DELETE', f'{self.base}/{feed["id"]}/assets/{asset["id"]}', optional=True)
        print('CNB 更新源已更新')
        release = self.release(tag, title, body)
        for path in installers:
            self.upload(release, path)
        self.request('PATCH', f'{self.base}/{release["id"]}', {'name': title, 'body': body, 'draft': False,
                                                                'prerelease': False, 'make_latest': 'true'})
        print('CNB Release 已发布')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, help='已通过验收的 HexCompanion.exe（文件夹版）')
    parser.add_argument('--check', type=Path, help='该 EXE 的验收报告')
    parser.add_argument('--notes', type=Path, help='Markdown 版本说明，同时用作 Release 正文和更新说明')
    parser.add_argument('--title', help='Release 标题，默认为版本号')
    parser.add_argument('--releases-dir', type=Path, default=ROOT / 'dist/velopack-releases',
                        help='保留历次完整包与差量包，供下一版生成差量')
    parser.add_argument('--keep-deltas', type=int, default=10, help='随本版一起上传的最近差量包数量')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--upload', action='store_true', help='上传到 GitHub 与 CNB；省略时只打包')
    mode.add_argument('--cnb-only', action='store_true',
                      help='只补传 CNB：不打包、不建标签、不动 GitHub，使用 --releases-dir 中已打好的本版文件')
    args = parser.parse_args()

    version, tag = __version__, f'v{__version__}'
    assert re.fullmatch(r'\d+\.\d+\.\d+', version), f'版本号需为 X.Y.Z：{version}'
    if (args.upload or args.cnb_only) and not (args.notes and os.environ.get('CNB_TOKEN')):
        parser.error('上传需要 --notes 和环境变量 CNB_TOKEN')
    if not args.cnb_only and not (args.exe and args.check):
        parser.error('打包需要 --exe 和 --check')
    if args.cnb_only and not git('ls-remote', '--tags', 'cnb', f'refs/tags/{tag}'):
        raise SystemExit(f'CNB 上没有标签 {tag}，请先用 --upload 完整发布。')
    title = args.title or tag
    notes = args.notes
    if notes is None:
        notes = args.releases_dir / f'notes-{version}.md'
        notes.parent.mkdir(parents=True, exist_ok=True)
        notes.write_text(f'海克斯随行 {tag}\n', encoding='utf-8')
    if args.upload:
        prepare_tag(tag)

    releases = args.releases_dir.resolve()
    if not args.cnb_only:
        exe = args.exe.resolve()
        package(exe, args.check)  # Same acceptance gate as the manual share package.
        pack(exe.parent, releases, version, notes.resolve())
    packages, installers, feed_path = stage(releases, version, args.keep_deltas)
    files = packages + installers
    result = {'version': version, 'pack_id': PACK_ID, 'feed': str(feed_path), 'uploaded': [],
              'files': [{'name': path.name, 'bytes': path.stat().st_size, 'sha256': sha(path)} for path in files]}
    if args.upload:
        publish_github(tag, title, notes, files, feed_path)
        result['uploaded'].append('github')
    if args.upload or args.cnb_only:
        prepare_feed_tag(tag)
        CNB(os.environ['CNB_TOKEN']).publish(tag, title, notes.read_text(encoding='utf-8'),
                                             packages, installers, feed_path)
        result['uploaded'].append('cnb')
    (ROOT / 'artifacts').mkdir(exist_ok=True)
    (ROOT / 'artifacts/update_release_result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                                              encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

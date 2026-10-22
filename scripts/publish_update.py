"""Pack an accepted folder build with Velopack and publish it to GitHub and CNB.

Without --upload the script stops after packing, so the feed and packages can be tried
against a local folder first. Uploading needs `gh` signed in, a `cnb` git remote and CNB_TOKEN.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from aram_demo import __version__
from aram_demo.updater import CNB_REPO, FEEDS, GITHUB_REPO, PACK_ID
from scripts.package_binary import package, sha

CNB_API = 'https://api.cnb.cool'
CHANNEL = 'win'
FEED = f'releases.{CHANNEL}.json'
INSTALLERS = (f'{PACK_ID}-{CHANNEL}-Setup.exe', f'{PACK_ID}-{CHANNEL}-Portable.zip')
GITHUB_FEED = dict(FEEDS)['GitHub']


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
    """The uploaded feed lists only files uploaded beside it: this full package and recent deltas."""
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
    files = [releases / asset['FileName'] for asset in full + deltas] + [releases / name for name in INSTALLERS]
    missing = [path.name for path in files if not path.is_file()]
    assert not missing, f'缺少待上传文件：{missing}'
    for asset in full + deltas:
        assert sha(releases / asset['FileName']) == asset['SHA256'].lower(), f'校验不符：{asset["FileName"]}'
    return files, feed_path


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

    def request(self, method, url, payload=None, missing_ok=False):
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
            raise SystemExit(f'CNB {method} {url} 返回 {exc.code}：{exc.read()[:500].decode(errors="replace")}')
        return json.loads(body) if body else {}

    def upload(self, release_id, path):
        size = path.stat().st_size
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
        print(f'已上传 CNB 附件：{path.name}')

    def publish(self, tag, title, body, files, feed_path):
        release = self.request('GET', f'{self.base}/tags/{urllib.parse.quote(tag, safe="")}', missing_ok=True)
        if release is None:
            release = self.request('POST', self.base, {'tag_name': tag, 'name': title, 'body': body, 'draft': True,
                                                       'prerelease': False, 'make_latest': 'false',
                                                       'target_commitish': 'main'})
        for path in [*files, feed_path]:
            self.upload(release['id'], path)
        self.request('PATCH', f'{self.base}/{release["id"]}', {'name': title, 'body': body, 'draft': False,
                                                                'prerelease': False, 'make_latest': 'true'})
        print('CNB Release 已发布')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, required=True, help='已通过验收的 HexCompanion.exe（文件夹版）')
    parser.add_argument('--check', type=Path, required=True, help='该 EXE 的验收报告')
    parser.add_argument('--notes', type=Path, help='Markdown 版本说明，同时用作 Release 正文和更新说明')
    parser.add_argument('--title', help='Release 标题，默认为版本号')
    parser.add_argument('--releases-dir', type=Path, default=ROOT / 'dist/velopack-releases',
                        help='保留历次完整包与差量包，供下一版生成差量')
    parser.add_argument('--keep-deltas', type=int, default=10, help='随本版一起上传的最近差量包数量')
    parser.add_argument('--upload', action='store_true', help='上传到 GitHub 与 CNB；省略时只打包')
    args = parser.parse_args()

    version, tag = __version__, f'v{__version__}'
    assert re.fullmatch(r'\d+\.\d+\.\d+', version), f'版本号需为 X.Y.Z：{version}'
    if args.upload and not (args.notes and os.environ.get('CNB_TOKEN')):
        parser.error('上传需要 --notes 和环境变量 CNB_TOKEN')
    title = args.title or tag
    notes = args.notes
    if notes is None:
        notes = args.releases_dir / f'notes-{version}.md'
        notes.parent.mkdir(parents=True, exist_ok=True)
        notes.write_text(f'海克斯随行 {tag}\n', encoding='utf-8')
    if args.upload:
        prepare_tag(tag)

    exe = args.exe.resolve()
    package(exe, args.check)  # Same acceptance gate as the manual share package.
    releases = args.releases_dir.resolve()
    pack(exe.parent, releases, version, notes.resolve())
    files, feed_path = stage(releases, version, args.keep_deltas)
    result = {'version': version, 'pack_id': PACK_ID, 'feed': str(feed_path), 'uploaded': [],
              'files': [{'name': path.name, 'bytes': path.stat().st_size, 'sha256': sha(path)} for path in files]}
    if args.upload:
        publish_github(tag, title, notes, files, feed_path)
        result['uploaded'].append('github')
        CNB(os.environ['CNB_TOKEN']).publish(tag, title, notes.read_text(encoding='utf-8'), files, feed_path)
        result['uploaded'].append('cnb')
    (ROOT / 'artifacts').mkdir(exist_ok=True)
    (ROOT / 'artifacts/update_release_result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                                              encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

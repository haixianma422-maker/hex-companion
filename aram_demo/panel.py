"""SELECT/GAME calibrated to the numbered logical-pixel V2 handoff."""
import os
import tkinter as tk
from .tk_images import WidgetPhotoImage
from .models import sort_champions, augment_label
from .builds import recommended_items
from .motion import Motion
from .motion_images import RegionTransition, dim_regions, visibility_image
from .ui_snapshot import snapshot
from .ui_drawing import (Artboard, ui_scale, position_window, Hint, measure, ellipsize,
                         BG,SURFACE,RAISED,TEXT,MUTED,LILAC,ACCENT,INK,INK_MUTED,LINE,UNKNOWN,TRANSPARENT)
from .ui_widgets import PixelButton, SourceSwitch
from .windows import prepare_popup, panel_position


class CompanionPanel:
    def __init__(self,root,on_scan,on_settings,on_hide,on_preview=None,on_source=None):
        self.window=tk.Toplevel(root); self.window.withdraw()
        self.window.title('海克斯随行 · 伴随浮窗'); self.window.overrideredirect(True)
        self.window.attributes('-topmost',True); self.window.configure(bg=TRANSPARENT)
        if os.name=='nt': self.window.attributes('-transparentcolor',TRANSPARENT)
        self.scale=ui_scale(root); self.width=round(360*self.scale); self.height=round(540*self.scale)
        self.dpi_scale=self.scale; self.zoom=1.; self.on_resize=None
        self._anchor=None; self._resize_origin=None; self._visibility_layer=None
        self._source_pending=False; self._source_old=None; self._transitions={}
        self.canvas=tk.Canvas(self.window,bg=TRANSPARENT,bd=0,highlightthickness=0,takefocus=True)
        self.canvas.pack(fill='both',expand=True); self.inner=self.canvas
        self.bitmap=self.canvas.create_image(0,0,anchor='nw')
        self.canvas.control_backdrop=self._control_backdrop
        self.motion=Motion(self.window)
        self.on_scan,self.on_settings,self.on_hide=on_scan,on_settings,on_hide
        self.on_source,self.on_preview=on_source,on_preview
        self.on_refresh=self.on_correct=None
        self.visible=False; self.context=None; self.signature=None; self.stage=None
        self.offset=self.base=(0,0); self._geometry=None; self._controls=[]
        self.item_icons=self.advice_icons=self.visual_assets=None
        self.source_name='OP.GG'; self.hotkey_bindings={'scan':'F6','refresh':'F7','toggle':'F8'}
        self.data_loading=self.images_loading=False; self.network_error=''; self.images_error=''
        self.manual_override=False; self.candidate_scroll=self.body_scroll=0
        self._candidate_target=0
        self.visible_height=540; self._regions=[]; self._strings=[]; self.assets_shown={}
        self.tip=Hint(self.canvas,''); self._tip_identity=None
        self.canvas.bind('<Motion>',self._hover)
        self.canvas.bind('<Leave>',lambda _:self.tip.hide())
        self.canvas.bind('<ButtonPress-1>',self._press)
        self.canvas.bind('<B1-Motion>',self._drag)
        self.canvas.bind('<ButtonRelease-1>',self._release)
        self.canvas.bind('<MouseWheel>',self._wheel)
        self.canvas.bind('<Escape>',lambda _:self.on_hide())
        self.canvas.bind('<Double-Button-1>',self._preview_switch)
        self._card_signatures=[]
        self._drag_origin=None; self._last=None
        prepare_popup(self.window)
        from .window_shadow import attach_shadow
        self.shadow=attach_shadow(self.window,self.scale,14)

    def set_motion(self,enabled):
        self.motion.set_enabled(enabled)
        for control in self._controls:
            control.set_motion(enabled)
        self.window.attributes('-alpha',1.)

    def set_zoom(self, zoom):
        """Keep the logical layout, images and hit regions on a single scale."""
        import math
        try: zoom=float(zoom)
        except (TypeError,ValueError): zoom=1.
        if not math.isfinite(zoom): zoom=1.
        height=580 if self.stage=='game' else 540
        maximum=2.5
        if self._anchor:
            l,t,r,b=self._anchor.work_area
            maximum=min(maximum,(r-l-12)/(360*self.dpi_scale),(b-t-12)/(height*self.dpi_scale))
        zoom=min(maximum,max(min(.65,maximum),zoom))
        if abs(zoom-self.zoom)<.001:return
        self.motion.cancel_all(finish=True)
        old_position=(self.window.winfo_rootx(),self.window.winfo_rooty()) if self._geometry else None
        self.zoom=zoom; self.scale=self.dpi_scale*zoom
        self.width=round(360*self.scale); self.height=round(height*self.scale)
        self.visible_height=height; self.body_scroll=self.candidate_scroll=0
        self._candidate_target=0; self._card_signatures=[]
        self._full_image=None; self._source_old=None; self._source_pending=False
        self.context=None; self.signature=None; self._geometry=None
        self.shadow.scale=self.scale
        if self.stage is not None:self._make_controls(self.stage)
        if self._last:self.render(*self._last)
        if self._anchor:
            if old_position:
                new_base=panel_position(self._anchor.rect,self._anchor.work_area,self.width,self.height)
                self.offset=(old_position[0]-new_base[0],old_position[1]-new_base[1])
            self.show_at(self._anchor)

    def set_hotkeys(self,bindings):
        self.hotkey_bindings=dict(bindings); self.signature=None
        if self._last: self.render(*self._last)

    def _text(self,art,box,text,size=14,bold=False,color=TEXT,**kwargs):
        self._strings.append(str(text))
        return art.text(box,str(text),size,bold,color,**kwargs)

    def _asset(self,kind,key):
        return self.visual_assets.path(kind,key) if self.visual_assets and key else None

    def _region(self,box,text='',action=None):
        self._regions.append((box,text,action))

    def _header(self,art,stage,preview):
        art.brand((16,10,20,20)); self._text(art,(45,8,190,24),'海克斯随行',17,True,line_height=24)
        if stage=='select': art.line((12,38,348,38),LINE)
        sy=55 if stage=='select' else 50
        art.circle((16,sy,8,8),ACCENT)
        self._text(art,(32,48 if stage=='select' else 43,100,22),
                   '选人中' if stage=='select' else '对局中' if stage=='game' else '等待连接',13,True)

    def _hero(self,art,state,champions,game=False):
        cid=state.champion_id; hero=champions.get(cid)
        info=self.visual_assets.champion_info(cid) if self.visual_assets and cid else {}
        name=info.get('name') or (hero.name if hero else '等待选择')
        title=info.get('title','') if cid else ''
        box=(4,68,352,138) if game else (6,75,348,106)
        art.rect(box,LILAC,8)
        image_box=(4,68,352,84) if game else box
        focus=self.visual_assets.champion_focus(cid) if self.visual_assets and cid else (.72,.42)
        path=self._asset('splash',cid)
        shown=art.image_at(image_box,path,hero=True,focus=focus,radius=8,round_bottom=not game)
        self.assets_shown[('splash',cid)]=shown
        if game:
            art.rect((4,152,352,54),LILAC,8)
            art.rect((4,152,352,8),LILAC)
        size=30 if game else 34
        width=130 if game else 110
        while size>24 and measure(name,size,True)>width: size-=1
        long=measure(name,size,True)>width
        self._text(art,(16,79,150 if long else 130,60 if long else 40) if game else (20,88 if long else 96,150 if long else 110,60 if long else 44),
                   name,size,True,INK,lines=2 if long else 1,line_height=30 if long else 40 if game else 44)
        self._text(art,(16,133 if long else 121,150,22) if game else (20,151 if long else 145,110 if long else 150,24),title,
                   14 if game else 15,True,INK_MUTED,line_height=22 if game else 24)
        if not game:
            tier=hero.tier_label if hero and hero.tier is not None else '—'
            pill=(134,155,30,22) if long else (134,110,30,22)
            art.rect(pill,'#D2C0EF',11); self._text(art,pill,tier,14,True,INK,align='center',line_height=20)
        if not shown and cid: self._region(image_box,'插画加载中' if self.images_loading else '暂无英雄插画，保留真实名称')
        return name

    def _advice(self,art,state,data,game=False):
        if state.stage not in ('select','game'):
            return
        valid=bool(data and data.get('champion_id')==state.champion_id and data.get('build_mode_verified') and data.get('build_mode')=='aram-mayhem')
        data=data if valid else{}
        if game:
            self._text(art,(16,170,78,20),'技能优先级',13,True,INK,line_height=20)
            keys=data.get('skill_priority',[])
            valid=len(keys)==2 and all(k in ('Q','W','E') for k in keys) and len(set(keys))==2
            if not valid:
                self._text(art,(98,160,246,40),'暂无推荐',14,color=INK,align='center'); return
            for i,key in enumerate(keys):
                x=98+i*48; box=(x,160,40,40)
                local_icons=self.visual_assets.champion_skill_icons(state.champion_id) if self.visual_assets else {}
                path=(self.advice_icons.path(data.get('skill_icons',{}).get(key,''))
                      or self.advice_icons.path(local_icons.get(key,''))) if self.advice_icons else None
                art.rect(box,'#D2C0EF',6)
                shown=art.image_at(box,path,radius=6,border='#CBBEE4')
                self.assets_shown[('skill',key)]=shown
                if not shown:art.icon('question',(x+8,166,24,24),INK)
                art.rect((x+26,184,14,16),BG,3)
                self._text(art,(x+26,184,14,16),key,11,True,TEXT,align='center',line_height=16)
                self._region(box,key+' 技能'+(' · 图标暂缺' if not shown else''))
            self._text(art,(198,170,146,20),f'主 {keys[0]} › 副 {keys[1]}',14,True,INK,line_height=20)
        else:
            self._text(art,(16,201,80,22),'召唤师技能',14,True,line_height=22)
            spells=data.get('summoner_spells',[])
            if len(spells)!=2:
                self._text(art,(102,195,151,32),'暂无推荐',12,align='center'); return
            for i,spell in enumerate(spells):
                x=102+i*86; box=(x,195,32,32)
                path=self.advice_icons.path(spell.get('icon_url','')) if self.advice_icons else None
                art.rect(box,SURFACE,6)
                shown=art.image_at(box,path,radius=6,border='#645775')
                self.assets_shown[('spell',spell.get('id'))]=shown
                if not shown:art.icon('question',(x+6,201,20,20),MUTED)
                self._text(art,(139+i*86,202,28,20),{6:'疾跑',11:'惩戒',12:'传送',13:'清晰',14:'点燃',21:'屏障'}.get(spell.get('id'),spell['name']),12,line_height=20)
                self._region((x,191,66,40),spell['name']+(' · 图标暂缺' if not shown else''))
            self._text(art,(170,202,12,20),'+',12,color=MUTED,align='center',line_height=20)
            if data.get('source_id')=='qq101' and data.get('summoner_source')=='opgg':
                self._text(art,(270,203,74,18),'OP.GG 补充',10,color=MUTED,align='right',line_height=18)

    def _candidates(self,art,state,champions):
        art.line((12,239,348,239),LINE)
        self._text(art,(16,252,90,26),'可选英雄',18,True,line_height=26)
        self._text(art,(108,257,150,20),'按梯队排序',12,color=MUTED,line_height=20)
        ids=list(dict.fromkeys(state.candidate_ids))
        ordered=[h.id for h in sort_champions([champions[i] for i in ids if i in champions])]+[i for i in ids if i not in champions]
        grid=Artboard(336,max(188,((len(ordered)+1)//2)*64-4),self.scale,bg=BG)
        self.candidate_scroll=max(0,min(self.candidate_scroll,max(0,grid.height-188)))
        self._candidate_target=max(0,min(self._candidate_target,max(0,grid.height-188)))
        self._candidate_rows=[]
        if not ids: self._text(art,(16,284,328,60),'等待客户端返回候选英雄',14,color=MUTED,align='center')
        for index,cid in enumerate(ordered):
            x,y=(index%2)*170,(index//2)*64
            selected=cid==state.champion_id; fill=LILAC if selected else SURFACE
            fg=INK if selected else TEXT; secondary=INK if selected else MUTED
            grid.rect((x,y,166,60),fill,10)
            if selected:grid.circle((x+4,y+26,7,7),ACCENT,INK,1)
            info=self.visual_assets.champion_info(cid) if self.visual_assets else{}
            hero=champions.get(cid); name=info.get('name') or (hero.name if hero else f'英雄{cid}')
            path=self._asset('portrait',cid); box=(x+14,y+9,42,42)
            grid.rect(box,RAISED,6)
            shown=grid.image_at(box,path,radius=6)
            self.assets_shown[('portrait',cid)]=shown
            if not shown:grid.text(box,name[:1],18,True,fg,align='center')
            size=13 if len(name)==4 and measure(name,14,True)>72 else 14
            self._text(grid,(x+66,y+16,72,26),name,size,True,fg,line_height=22)
            self._text(grid,(x+138,y+16,24,26),hero.tier_label if hero and hero.tier is not None else'—',14,True,secondary,align='right',line_height=22)
            self._candidate_rows.append((x,y,name+' · '+(info.get('title') or '暂无档位')))
        self.candidate_content_height=grid.height
        self._candidate_grid=grid
        self._candidate_pixels=grid.finish()
        self._candidate_thumb=None
        if grid.height>188:
            thumb=max(24,188*188/grid.height)
            marker=Artboard(4,thumb,self.scale,bg=(0,0,0,0))
            marker.rect((0,0,4,thumb),'#665974',2)
            self._candidate_thumb=marker.finish()
        self._candidate_hit_regions=self._candidate_regions()
        self._regions.extend(self._candidate_hit_regions)
        view=self._candidate_view()
        art.image.alpha_composite(view.image,(round(12*art.factor),round(284*art.factor)))

    def _candidate_regions(self):
        result=[]
        for x,y,text in self._candidate_rows:
            display_y=284+y-self.candidate_scroll
            if display_y<472 and display_y+60>284:
                result.append(((12+x,max(284,display_y),166,min(472,display_y+60)-max(284,display_y)),text,None))
        return result

    def _candidate_view(self):
        grid=self._candidate_grid; f=grid.factor
        start=round(self.candidate_scroll*f)
        view=Artboard(336,188,self.scale,bg=BG)
        view.image.alpha_composite(grid.image.crop((0,start,round(336*f),start+round(188*f))))
        if grid.height>188:
            thumb=max(24,188*188/grid.height)
            sy=(188-thumb)*self.candidate_scroll/(grid.height-188)
            view.rect((332,sy,4,thumb),'#665974',2)
        return view

    def _move_candidates(self,value):
        limit=max(0,self.candidate_content_height-188)
        self.candidate_scroll=max(0,min(value,limit))
        start=round(self.candidate_scroll*self.scale)
        view=self._candidate_pixels.crop((0,start,round(336*self.scale),start+round(188*self.scale)))
        if self._candidate_thumb is not None:
            sy=(188*self.scale-self._candidate_thumb.height)*self.candidate_scroll/limit
            view.alpha_composite(self._candidate_thumb,(round(332*self.scale),round(sy)))
        self._full_image.paste(view,(round(12*self.scale),round(284*self.scale)))
        self._candidate_hit_regions=self._candidate_regions()
        self._regions=self._candidate_fixed_regions+self._candidate_hit_regions
        self._display_image()

    def _scroll_candidates(self,target):
        self._candidate_target=max(0,min(target,max(0,self.candidate_content_height-188)))
        self.motion.animate('candidate-scroll',self.candidate_scroll,self._candidate_target,
                            self._move_candidates,140)

    def _game(self,art,state,data,matches):
        self._text(art,(14,217,170,26),'海克斯推荐',17,True,line_height=26)
        index={a['id']:a for a in (data or{}).get('augments',[])}
        recognized=0
        colors={'S':ACCENT,'A':LILAC,'B':'#D6C8ED','C':'#C4B3DD','D':'#B3A3C9','E':'#A796BA'}
        for slot in range(3):
            x=14+slot*112; match=next((m for m in matches if m.slot==slot),None)
            augment=index.get(match.augment_id) if match else None
            grade=augment_label(augment.get('tier'),(data or{}).get('tier_labels')) if augment else'—'
            if grade not in colors:grade='—'
            recognized+=bool(augment)
            fill=colors.get(grade,'#B3A3C9'); art.rect((x,244,108,126),fill,10)
            self._text(art,(x+6,250,96,18),('左侧','中间','右侧')[slot],11,color=INK,align='center',line_height=18)
            self._text(art,(x+10,269,52,61),grade,52,True,INK,align='center',line_height=61,optical=True)
            icon_box=(x+62,275,38,38); path=self._asset('augment',augment['id']) if augment else None
            shown=art.image_at(icon_box,path,fit='contain',radius=0)
            if augment:self.assets_shown[('augment',augment['id'])]=shown
            if not shown:art.icon('question',icon_box,INK,1.6)
            name=augment['name'] if augment else '待确认'
            long=len(name)>5
            self._text(art,(x+6,319 if long else 321,96,34 if long else 22),name,12 if long else 14,True,INK,
                       align='center',lines=2 if long else 1,line_height=17 if long else 22)
            hint='手动修正' if augment and self.manual_override else'已识别' if grade!='—' else'暂无评级' if augment else'点击修正' if match and match.text else'等待识别'
            self._text(art,(x+6,353 if long else 348,96,16 if long else 18),hint,11,color=INK,align='center',line_height=16 if long else 18)
            if grade=='S':art.icon('star',(x+90,251,10,12),INK,1)
            self._region((x,244,108,126),name+(' · 图标暂缺' if augment and not shown else'')+' · 点击手动修正',
                         lambda i=slot:self.on_correct(i) if self.on_correct else None)
        self._text(art,(253,220,93,20),f'已识别 {recognized} / 3',12,color=MUTED,align='right',line_height=20)
        if self._source_pending:
            art.rect((174,218,175,23),BG)
            self._text(art,(174,218,171,23),'正在切换来源…',12,color=MUTED,align='right')
        elif not self._scanning and ('未能确认' in self._status or '截图失败' in self._status or '识别失败' in self._status):
            art.rect((14,218,335,23),BG)
            self._text(art,(14,218,335,23),self._status,12,color=MUTED)
        art.line((14,382,346,382),LINE)
        self._text(art,(14,389,96,24),'核心出装',17,True,line_height=24)
        self._text(art,(117,392,180,20),'英雄 / 模式推荐',11,color=MUTED,line_height=20)
        verified=data and data.get('champion_id')==state.champion_id and data.get('build_mode_verified') and data.get('build_mode')=='aram-mayhem'
        items=recommended_items(data) if verified else[]
        short={3085:'卢安娜飓风',3036:'多米尼克',3006:'狂战士胫甲'}
        for i in range(4):
            item=items[i] if i<len(items) else None; x=20+i*86
            art.rect((x,416,62,62),SURFACE,6)
            path=self.item_icons.path(item['id']) if self.item_icons and item else None
            shown=art.image_at((x,416,62,62),path,radius=6,border='#645775')
            if item:self.assets_shown[('item',item['id'])]=shown
            if not shown:art.icon('question',(x+19,435,24,24),MUTED)
            name=short.get(item['id'],item['name']) if item else'暂无资料'
            self._text(art,(14+i*86,484,74,34),name,12,lines=2,line_height=17,align='center')
            self._region((14+i*86,416,74,102),(item['name'] if item else'暂无装备推荐')+(' · 图标暂缺' if item and not shown else''))

    def _footer(self,art,game):
        y=560 if game else 482
        art.line((14 if game else 12,y,346 if game else 348,y),LINE)
        caption=self.source_name+' · '+('加载中' if self.data_loading else'暂无资料' if not self._has_data else'缓存资料')
        self._text(art,(14,565,246,14) if game else(16,491,230,20),caption,10 if game else 12,color=MUTED,line_height=14 if game else 20)
        self._text(art,(280,565,66,14) if game else(145,520,90,18),self.hotkey_bindings['toggle']+' 收起',10 if game else 11,color=MUTED,
                   align='right' if game else'center',line_height=14 if game else 18)
        self._region((14,560,246,20) if game else(16,486,230,30),self._status+'\n'+self.network_error)
        self._region((280,562,66,18) if game else(145,516,90,24),'收起海克斯随行',self.on_hide)

    def _make_controls(self,stage):
        for control in self._controls:control.destroy()
        self._controls=[]
        def btn(text,action,w,h,kind='ghost',icon=None):
            control=PixelButton(self.canvas,text,action,w,h,kind=kind,icon=icon,scale=self.scale)
            control.set_motion(self.motion.enabled); self._controls.append(control); return control
        self.collapse_button=btn('',self.on_hide,28,28,icon='minus')
        self.settings_button=btn('',self.on_settings,28,28,icon='settings')
        self.collapse_button.configure(color=MUTED); self.settings_button.configure(color=MUTED)
        Hint(self.collapse_button,'收起为浮标'); Hint(self.settings_button,'设置')
        self.quick_source_var=tk.StringVar(value=self.source_name)
        self.source_picker=SourceSwitch(self.canvas,self.quick_source_var,{'OP.GG':'OP.GG','101':'101 数据站'},
                                        scale=self.scale,on_change=lambda value:self.on_source(value) if self.on_source else None)
        self.source_picker.set_motion(self.motion.enabled); self._controls.append(self.source_picker)
        self.scan_button=None
        if stage=='game':
            self.scan_button=btn('',self.on_scan,180,34,'primary','scan')
            self.refresh_button=btn('',lambda:self.on_refresh() if self.on_refresh else None,36,34,'secondary','refresh')
        else:self.refresh_button=btn('',lambda:self.on_refresh() if self.on_refresh else None,80,28,icon='refresh')
        self.refresh_tip=Hint(self.refresh_button,'刷新资料')
        self._position_controls()

    def _position_controls(self):
        game=self.stage=='game'; delta=self.visible_height-(580 if game else 540)
        self.collapse_button.place_logical(287,4); self.settings_button.place_logical(321,4)
        self.source_picker.place_logical(236,42 if game else 46)
        refresh_key=self.hotkey_bindings['refresh']; self.refresh_tip.text='刷新资料（'+refresh_key+'）'
        if game:
            key=self.hotkey_bindings['scan']; long=len(key)>4
            self.scan_button.set_size(220 if long else 180,34)
            label='识别中…' if self._scanning else '重新识别 '+key
            group_width=measure(label,14,True)+24
            group_x=(220-group_width)/2
            self.scan_button.configure(text=label, state='normal', icon_box=(13 if not long else max(6,group_x),9,16,16), text_box=(40 if not long else max(30,group_x+24),6,114 if not long else 184,22))
            self.scan_button.set_task_active(self._scanning and self.visible)
            self.scan_button.place_logical(32 if long else 60,522+delta)
            if hasattr(self.scan_button,'set_size'):self.scan_button.set_size(220 if long else 180,34)
            self.refresh_button.place_logical(264 if long else 250,522+delta)
            self.refresh_button.configure(text=refresh_key if len(refresh_key)<=4 else '', font_size=10, bold=False, color=MUTED, icon_color=TEXT, icon_box=(11,5,14,14), text_box=(10,22,16,12))
        else:
            self.refresh_button.configure(text='刷新 '+refresh_key if len(refresh_key)<=4 else '刷新', font_size=12, bold=False, color=MUTED, icon_box=(0,6,16,16), text_box=(21,3,59,22))
            self.refresh_button.place_logical(266,486+delta)

    def render(self,state,champions,data,matches,status,preview=False,scanning=False):
        self._last=(state,champions,data,matches,status,preview,scanning)
        current=data or {}
        matched_ids={match.augment_id for match in matches}
        advice_key=(current.get('champion_id'),current.get('build_mode_verified'),current.get('build_mode'),
                    tuple(current.get('skill_priority',[])),tuple(sorted(current.get('skill_icons',{}).items())),
                    tuple((spell.get('id'),spell.get('name'),spell.get('icon_url')) for spell in current.get('summoner_spells',[])),
                    current.get('source_id'),current.get('summoner_source'))
        visible_data_key=(advice_key,
                          tuple((a.get('id'),a.get('name'),a.get('tier')) for a in current.get('augments',[]) if a.get('id') in matched_ids),
                          tuple((item.get('id'),item.get('name')) for item in recommended_items(current)),
                          tuple(sorted(current.get('tier_labels',{}).items())))
        key=(state.stage,state.champion_id,tuple(state.candidate_ids),(data or{}).get('fetched_at'),self.source_name,
             tuple((m.slot,m.augment_id,m.status,m.text) for m in matches),status,scanning,self.data_loading,
             self.images_loading,self.network_error,self.manual_override,tuple(self.hotkey_bindings.items()),self.visible_height,
             visible_data_key)
        if self.signature==key:return
        same_context = self.context == (state.stage,state.champion_id,self.source_name)
        # Repaints in the same context (an image or data load finishing) move a
        # running transition to the new picture instead of cutting it to its end.
        retarget={name:self._transitions[name] for name in ('hero','cards','source')
                  if same_context and name in self.motion.jobs and name in self._transitions}
        for name in ('hero','cards','source'):
            if name not in retarget:self.motion.cancel(name,finish=True)
        if 'visibility' in self.motion.jobs and not same_context:self.motion.cancel('visibility',finish=True)
        previous=getattr(self,'_full_image',None)
        old_context=self.context
        resume_scroll='candidate-scroll' in self.motion.jobs
        self.motion.cancel('candidate-scroll')
        source_changed = bool(self.context and self.context[:2] == (state.stage,state.champion_id)
                              and self.context[2] != self.source_name)
        hero_changed=bool(old_context and old_context[0]==state.stage=='select' and old_context[1]!=state.champion_id)
        if source_changed:
            self._source_old=previous
            self._source_pending=True
        elif old_context and old_context[:2]!=(state.stage,state.champion_id):
            self._source_old=None; self._source_pending=False
        source_ready=self._source_pending and not self.data_loading and not self.network_error and bool(data)
        if source_ready:self._source_pending=False
        if self._source_pending and self.network_error and not self.data_loading:
            self._source_pending=False; self._source_old=None
        if self.context and not same_context:
            self.tip.hide(); self.body_scroll=self.candidate_scroll=0
            self._candidate_target=0; resume_scroll=False
            self.motion.cancel('visibility', finish=self.visible)
            self.motion.cancel_all()
        changed_stage=self.stage!=state.stage
        self.stage=state.stage; self.context=(state.stage,state.champion_id,self.source_name)
        self._status=status; self._has_data=bool(data); self._scanning=scanning
        if changed_stage:
            self.visible_height=580 if state.stage=='game' else 540; self.body_scroll=0
            self._make_controls(state.stage)
        elif self.quick_source_var.get()!=self.source_name:
            self.tip.hide(); self.quick_source_var.set(self.source_name)
        self.signature=key; self._regions=[]; self._strings=[]; self.assets_shown={}
        game=state.stage=='game'; height=580 if game else 540
        art=Artboard(360,height,self.scale,bg=TRANSPARENT); art.rect((0,0,360,height),BG,14)
        self._header(art,state.stage,preview); self._hero(art,state,champions,game); self._advice(art,state,data,game)
        if game:self._game(art,state,data,matches)
        else:self._candidates(art,state,champions)
        self._footer(art,game)
        if not game:
            self._candidate_fixed_regions=[region for region in self._regions if region not in self._candidate_hit_regions]
        current=art.finish()
        previous_cards=self._card_signatures
        new_cards=[(m.slot,m.augment_id,m.status,m.text) for m in matches] if game else []
        for name,transition in list(retarget.items()):
            if transition.old.size==current.size:transition.retarget(current)
            else:
                del retarget[name]; self.motion.cancel(name,finish=True)
        self._full_image=next((t.frame(t.progress) for t in retarget.values()),current)
        self._display_image(); self._position_controls()
        self._card_signatures=new_cards
        if (source_changed or self._source_pending or source_ready) and self._source_old is not None and self._source_old.size==current.size:
            regions=self._source_regions(game)
            waiting=dim_regions(self._source_old,current,regions,self.scale)
            if self._source_pending:
                self._full_image=waiting; self._display_image()
            else:
                self._image_transition('source',waiting,current,regions,160)
                self._source_old=None
        elif source_changed:
            self._source_transition(current,game)
        elif hero_changed and previous is not None and previous.size==current.size:
            self._image_transition('hero',previous,current,[(6,75,348,106),(12,284,336,124)],180,shift=3)
        elif resume_scroll and not game:
            self._scroll_candidates(self._candidate_target)
        if game and same_context and not changed_stage and previous is not None and previous.size==current.size and previous_cards!=new_cards:
            old_by_slot={row[0]:row for row in previous_cards}; new_by_slot={row[0]:row for row in new_cards}
            changed=[i for i in range(3) if old_by_slot.get(i)!=new_by_slot.get(i)]
            if not self._source_pending and not source_ready:
                self._image_transition('cards',previous,current,[(14+i*112,244,108,126) for i in changed],
                    180,shift=4,base='old',radius=10)

    def _image_transition(self,name,previous,current,regions,duration,**kwargs):
        transition=RegionTransition(previous,current,regions,self.scale,**kwargs)
        self._transitions[name]=transition
        def update(progress):
            self._full_image=transition.frame(progress); self._display_image()
        self.motion.animate(name,0.,1.,update,duration)

    def _source_regions(self,game):
        return [(4,152,352,54),(12,244,336,276)] if game else [(6,187,348,48),(12,284,336,188)]

    def _source_transition(self,current,game):
        waiting=dim_regions(current,current,self._source_regions(game),self.scale)
        self._image_transition('source',waiting,current,self._source_regions(game),160)

    def _display_image(self):
        game=self.stage=='game'; base=580 if game else 540
        full=self._full_image; s=self.scale; footer=522 if game else 482; top=68 if game else 75
        target=round(self.visible_height*s)
        if target!=full.height:
            from PIL import Image
            result=Image.new('RGBA',(full.width,target),TRANSPARENT)
            hp=round(top*s); fh=round((base-footer)*s); mid=max(0,target-hp-fh)
            result.paste(full.crop((0,0,full.width,hp)),(0,0))
            start=round((top+self.body_scroll)*s)
            result.paste(full.crop((0,start,full.width,start+mid)),(0,hp))
            result.paste(full.crop((0,round(footer*s),full.width,full.height)),(0,target-fh))
            from PIL import ImageDraw
            available=base-top-(base-footer)
            thumb=max(round(24*s),mid*mid/(available*s))
            sy=hp+(mid-thumb)*self.body_scroll/max(1,base-self.visible_height)
            ImageDraw.Draw(result).rounded_rectangle((round(350*s),round(sy),round(354*s)-1,round(sy+thumb)),radius=round(2*s),fill='#60576F')
        else:result=full
        self._visible_image=result
        self.photo=WidgetPhotoImage(result,master=self.canvas)
        self.canvas.itemconfigure(self.bitmap,image=self.photo)

    def _control_backdrop(self,x,y,w,h):
        image=getattr(self,'_visible_image',None)
        if image is None:return None
        return image.crop(tuple(round(v*self.scale) for v in (x,y,x+w,y+h)))

    def _logical(self,event):
        x,y=event.x/self.scale,event.y/self.scale
        game=self.stage=='game'; base=580 if game else 540; footer=522 if game else 482; top=68 if game else 75
        if self.visible_height<base:
            visible_footer=self.visible_height-(base-footer)
            if y>=visible_footer:y+=base-self.visible_height
            elif y>=top:y+=self.body_scroll
        return x,y

    def _hit(self,event):
        x,y=self._logical(event)
        return next((r for r in reversed(self._regions) if r[0][0]<=x<r[0][0]+r[0][2] and r[0][1]<=y<r[0][1]+r[0][3]),None)

    def _hover(self,event):
        if self._resize_hit(event):
            self.tip.hide(); self.canvas.configure(cursor='size_nw_se'); return
        hit=self._hit(event); identity=hit[0] if hit else None
        if identity!=self._tip_identity:
            self.tip.text=hit[1] if hit else''; self._tip_identity=identity
            if hit:self.tip._enter()
        self.canvas.configure(cursor='hand2' if hit and hit[2] else'')

    def _preview_switch(self,event):
        if self.on_preview and event.y/self.scale<38:
            self._drag_origin=None
            self.on_preview()
            return 'break'

    def _press(self,event):
        self.tip.hide()
        if self._resize_hit(event):
            self.motion.cancel_all(finish=True)
            self._resize_origin=(event.x_root,event.y_root,self.zoom)
            self._drag_origin=None; return
        if event.y/self.scale<38:self._drag_origin=(event.x_root,event.y_root,self.window.winfo_rootx(),self.window.winfo_rooty())

    def _drag(self,event):
        if self._resize_origin:
            sx,sy,zoom=self._resize_origin
            height=580 if self.stage=='game' else 540
            dx,dy=event.x_root-sx,event.y_root-sy
            growth=(dx*360+dy*height)/(360**2+height**2)/self.dpi_scale
            self.set_zoom(zoom+growth); return
        if self._drag_origin:
            sx,sy,x,y=self._drag_origin
            x+=event.x_root-sx; y+=event.y_root-sy
            if self._anchor:
                l,t,r,b=self._anchor.work_area
                x=max(l,min(x,r-self.width)); y=max(t,min(y,b-self.height))
            self.offset=(x-self.base[0],y-self.base[1]); position_window(self.window,x,y)
            self._geometry=(x,y,self.width,self.height)

    def _release(self,event):
        if self._resize_origin:
            self._drag(event); self._resize_origin=None
            if self.on_resize:self.on_resize(self.zoom)
            return
        if self._drag_origin:self._drag_origin=None; return
        hit=self._hit(event)
        if hit and hit[2]:hit[2]()

    def _resize_hit(self,event):
        return event.x>=self.width-14*self.scale and event.y>=self.height-14*self.scale

    def _wheel(self,event):
        if not event.delta:return 'break'
        self.tip.hide(); x,y=self._logical(event); step=-32*event.delta/120
        base=580 if self.stage=='game' else 540
        if self.visible_height<base:self.body_scroll=max(0,min(base-self.visible_height,self.body_scroll+step))
        elif self.stage!='game' and 284<=y<=472:
            self.motion.cancel('source',finish=True)
            if (self._candidate_target-self.candidate_scroll)*step<0:
                self._candidate_target=self.candidate_scroll
            self._scroll_candidates(self._candidate_target+step)
            return 'break'
        else:return
        self.signature=None
        if self._last:self.render(*self._last)
        return 'break'

    def show_at(self,anchor):
        self._anchor=anchor
        work=anchor.work_area; base_height=580 if self.stage=='game' else 540
        maximum=min(2.5,(work[2]-work[0]-12)/(360*self.dpi_scale),
            (work[3]-work[1]-12)/(base_height*self.dpi_scale))
        # Retain the default-size middle scrollbar on short work areas, while
        # user-scaled windows and narrow monitors fit the whole surface.
        if self.zoom>maximum+.001 and (abs(self.zoom-1.)>.001 or self.width>work[2]-work[0]-12):
            self.set_zoom(maximum)
            return
        height=min(round(base_height*self.scale),work[3]-work[1]-12)
        logical=height/self.scale
        if self.visible_height!=logical:
            self.visible_height=logical; self.signature=None
            if self._last:self.render(*self._last)
        self.height=height
        self.base=panel_position(anchor.rect,work,self.width,height)
        x=max(work[0],min(self.base[0]+self.offset[0],work[2]-self.width))
        y=max(work[1],min(self.base[1]+self.offset[1],work[3]-height))
        geometry=(x,y,self.width,height)
        if geometry!=self._geometry:
            if self.visible:
                self.motion.cancel('visibility',finish=True)
                self.window.attributes('-alpha',1.)
            position_window(self.window,*geometry)
            self._geometry=geometry
        if not self.visible:
            self.motion.cancel('visibility',finish=True); self.visible=True
            self.window.attributes('-alpha',0. if self.motion.enabled else 1.)
            self.window.deiconify()
            self.window.update_idletasks()
            position_window(self.window,x,y,self.width,height)
            self._position_controls()
            self._visibility_transition(True)

    def _visibility_transition(self,show,done=None):
        picture=None
        if self.motion.enabled:
            picture=snapshot(self.window)
        if picture is not None:
            if self._visibility_layer is None:
                self._visibility_layer=tk.Canvas(self.window,bd=0,highlightthickness=0,bg=TRANSPARENT)
                self._visibility_bitmap=self._visibility_layer.create_image(0,0,anchor='nw')
                self._visibility_layer.bind('<ButtonPress-1>',lambda _:self.motion.cancel('visibility',finish=True))
            self._visibility_layer.place(x=0,y=0,width=self.width,height=self.height)
            tk.Misc.lift(self._visibility_layer)
        def update(progress):
            amount=progress if show else 1-progress
            self.window.attributes('-alpha',amount)
            if picture is not None:
                self._visibility_photo=WidgetPhotoImage(visibility_image(picture,amount,self.scale),master=self._visibility_layer)
                self._visibility_layer.itemconfigure(self._visibility_bitmap,image=self._visibility_photo)
        def finish():
            if self._visibility_layer is not None:self._visibility_layer.place_forget()
            if not show:self.window.withdraw()
            self.window.attributes('-alpha',1.)
            self._visibility_photo=None
            if done:done()
        self.motion.animate('visibility',0.,1.,update,320 if show else 260,done=finish)

    def hide(self,animate=False,done=None):
        self.tip.hide()
        for name in ('hero','cards','source'):
            self.motion.cancel(name,finish=True)
        self._candidate_target=self.candidate_scroll
        if self.visible:
            self.motion.cancel('visibility',finish=True)
            self.visible=False; self.motion.cancel_all()
            if getattr(self,'scan_button',None):self.scan_button.set_task_active(False)
            if animate and self.motion.enabled:
                self._visibility_transition(False,done)
            else:
                if self._visibility_layer is not None:self._visibility_layer.place_forget()
                self.window.withdraw(); self.window.attributes('-alpha',1.)
                if done:done()
        elif not animate:
            self.motion.cancel_all(); self.window.withdraw(); self.window.attributes('-alpha',1.)
            if self._visibility_layer is not None:self._visibility_layer.place_forget()
            if getattr(self,'scan_button',None):self.scan_button.set_task_active(False)
            if done:done()
        elif 'visibility' not in self.motion.jobs and done:done()

    def content_text(self):return '\n'.join(self._strings)

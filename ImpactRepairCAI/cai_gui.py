# -*- coding: utf-8 -*-
from abaqusGui import *
import json
import os
from cai_config import DEFAULTS, load, validate, dump, native_text


def text(value):
    return native_text(value)


class ImpactRepairForm(AFXForm):
    def __init__(self,owner):
        AFXForm.__init__(self,owner)
        self.command=AFXGuiCommand(self,method='execute',objectName='cai_kernel')
        self.config_path=AFXStringKeyword(self.command,'config_path',True,'')
        self.action=AFXStringKeyword(self.command,'action',True,'inspect')
        self.overrides=AFXStringKeyword(self.command,'overrides_json',True,'{}')
        self.kw={}
        for key,value in DEFAULTS.items():
            if isinstance(value,bool):
                self.kw[key]=AFXBoolKeyword(None,key,AFXBoolKeyword.TRUE_FALSE,True,value)
            elif isinstance(value,int): self.kw[key]=AFXIntKeyword(None,key,True,value)
            elif isinstance(value,float): self.kw[key]=AFXFloatKeyword(None,key,True,value)
            else: self.kw[key]=AFXStringKeyword(None,key,True,value)

    def getFirstDialog(self):
        return ImpactRepairDialog(self)

    def settings(self):
        cfg=dict((key,keyword.getValue()) for key,keyword in self.kw.items())
        return load(overrides=cfg)

    def getKernelInitializationCommand(self):
        return 'import cai_kernel'


class FilePicker(FXObject):
    def __init__(self,keyword,pattern):
        FXObject.__init__(self)
        self.keyword=keyword; self.pattern=pattern
        self.readonly=AFXBoolKeyword(None,'readOnly',AFXBoolKeyword.TRUE_FALSE)
        self.pattern_target=AFXIntTarget(0)
        FXMAPFUNC(self,SEL_COMMAND,AFXMode.ID_ACTIVATE,FilePicker.activate)

    def activate(self,sender,sel,ptr):
        dialog=AFXFileSelectorDialog(getAFXApp().getAFXMainWindow(),text('选择文件'),
            self.keyword,self.readonly,AFXSELECTFILE_ANY,self.pattern,self.pattern_target)
        dialog.create(); dialog.showModal()
        return 1


class ImpactRepairDialog(AFXDataDialog):
    (ID_INSPECT,ID_BUILD,ID_CHECK,ID_SUBMIT,ID_RESULTS,ID_REPORT,ID_LOAD,ID_SAVE)=range(AFXDataDialog.ID_LAST,AFXDataDialog.ID_LAST+8)

    def __init__(self,form):
        AFXDataDialog.__init__(self,form,text('冲击后贴补与 CAI — Abaqus 2024'),0,DIALOG_ACTIONS_SEPARATOR)
        self.form=form; self.pickers=[]
        self.appendActionButton(text('生成模型'),self,self.ID_BUILD)
        self.appendActionButton(text('开始计算'),self,self.ID_SUBMIT)
        self.appendActionButton(self.CANCEL)
        self.getActionButton(self.ID_CLICKED_CANCEL).setText(text('关闭'))
        for event,method in ((self.ID_INSPECT,ImpactRepairDialog.inspect),(self.ID_BUILD,ImpactRepairDialog.build),
            (self.ID_CHECK,ImpactRepairDialog.check),(self.ID_SUBMIT,ImpactRepairDialog.submit),(self.ID_RESULTS,ImpactRepairDialog.results),
            (self.ID_REPORT,ImpactRepairDialog.report),(self.ID_LOAD,ImpactRepairDialog.load_config),(self.ID_SAVE,ImpactRepairDialog.save_config)):
            FXMAPFUNC(self,SEL_COMMAND,event,method)
        # AFXDataDialog uses FXPacker: an expanding tab book consumes the
        # remaining cavity. A vertical content frame reserves space for later rows.
        content=FXVerticalFrame(self,opts=LAYOUT_FILL_X|LAYOUT_FILL_Y,pl=0,pr=0,pt=0,pb=0)
        FXLabel(content,text('原母板网格与材料状态继承；新补片保持平整；结果按母板名义截面积归一化。'))
        tabs=FXTabBook(content,None,0,LAYOUT_FILL_X|LAYOUT_FILL_Y)
        source=self.tab(tabs,'1  冲击数据')
        for key,label,pattern in (
            ('source_inp','冲击 INP','*.inp'),('source_odb','冲击 ODB','*.odb'),
            ('vumat','原作业 VUMAT','*.for,*.f')):
            self.file_row(source,key,label,pattern)
        for key,label in (('source_instance','母板实例名'),
            ('base_material','原母板材料名'),('interply_material','原层间材料名')):
            self.field(source,key,label)
        FXLabel(source,text('自动选取最后分析步的最后一帧，并匹配实际保存状态。\n若最后一帧未保存状态，显示并采用最后可匹配保存点；详情见消息区。'))
        patch=self.tab(tabs,'2  补片参数')
        self.patch_panel=patch
        self.combo(patch,'shape','形状：circle 圆 / rectangle 矩形 / ellipse 椭圆',('circle','rectangle','ellipse'))
        self.combo(patch,'sides','贴补面：top 上 / bottom 下 / both 双面',('top','bottom','both'))
        self.combo(patch,'bond_void_policy','缺口：reject 停止 / bridge 补片跨越且缺口不涂胶',('reject','bridge'))
        for key,label in (('size_x','X 尺寸 / mm（圆：直径；椭圆：完整轴长）'),
            ('size_y','Y 尺寸 / mm（圆形忽略）'),('corner_radius','四周圆角半径 / mm（仅矩形，0 为直角）'),
            ('ply_count','每侧铺层数'),('angles','铺层角度 / deg（用 / 分隔）'),
            ('mesh_size','补片平面网格尺寸 / mm')):
            self.field(patch,key,label)
        FXLabel(patch,text('补片自动居中，椭圆长轴与母板长轴平行；矩形边与母板边平行。\n单层及层间厚度自动继承母板。双面共用参数，铺层角度仍相对于全局 X。'))
        film=self.tab(tabs,'3  LJM-170 胶层')
        self.film_panel=film
        for key,label in (('adhesive_min_thickness','最小胶厚 / mm'),('adhesive_E','法向模量 E / MPa'),
            ('adhesive_G','剪切模量 G / MPa'),('adhesive_tn','法向损伤起始强度 / MPa'),
            ('adhesive_ts','剪切损伤起始强度 / MPa'),('adhesive_GIc','GIc / N/mm'),
            ('adhesive_GIIc','GIIc = GIIIc / N/mm'),('adhesive_BK','BK 指数（待标定）'),
            ('adhesive_density','密度 / tonne/mm3（待核实）')):
            self.field(film,key,label)
        FXLabel(film,text('胶层填充残余凹陷，采用几何厚度作为本构厚度。\nE/G、强度和断裂能来源：力学与实践 2026，48(1):55–62，表 2。\nDOI: 10.6052/1000-0879-25-181。该预设为文献参考，非本工艺标定值。\nBK=1.5、密度=1.2e-9 为可编辑初始假设。'))
        analysis=self.tab(tabs,'4  CAI 与输出')
        mode=AFXComboBox(analysis,28,2,text('分析类型：'),form.kw['analysis_mode'],0)
        mode.appendItem(text('冲击后压缩（不引入补片）'),0)
        mode.appendItem(text('修补后压缩（使用补片与胶层）'),1)
        FXLabel(analysis,text('母板及损伤状态直接继承冲击文件；压缩轴固定为 X。\n场/历史输出沿用冲击文件；补充两端反力与能量用于强度计算。'))
        for key,label in (('end_support_width','端部防屈曲支撑带宽 / mm'),('side_support_width','侧边支撑带宽 / mm（0 为边线）'),
            ('relax_time','压缩前平衡时间 / s'),('compression_time','压缩加载时间 / s'),
            ('displacement','压缩位移幅值 / mm（正数）'),('cpus','CPU 数'),
            ('job_name','模型 / 作业名（英文）'),('output_dir','独立输出目录（空白则自动生成）')):
            self.field(analysis,key,label)
        FXLabel(analysis,text('边界为参考 D7137 的工程等效约束，并非完整标准夹具验证。\n几何非线性开启；默认不进行质量缩放。未出现峰后下降时只报告已观察峰值。'))
        actions=FXHorizontalFrame(content,opts=LAYOUT_FILL_X)
        for label,event in (('检查源文件',self.ID_INSPECT),('输入检查',self.ID_CHECK),('提取结果',self.ID_RESULTS),('刷新报告',self.ID_REPORT)):
            FXButton(actions,text(label),None,self,event)
        settings=FXHorizontalFrame(content,opts=LAYOUT_FILL_X)
        AFXTextField(settings,36,text('配置 JSON：'),form.config_path,0)
        picker=FilePicker(form.config_path,'*.json'); self.pickers.append(picker)
        FXButton(settings,'...',None,picker,AFXMode.ID_ACTIVATE)
        FXButton(settings,text('载入配置'),None,self,self.ID_LOAD)
        FXButton(settings,text('保存配置'),None,self,self.ID_SAVE)
        self.status=FXText(content,opts=TEXT_READONLY|TEXT_WORDWRAP|LAYOUT_FILL_X|LAYOUT_FIX_HEIGHT,h=60)
        self.status.setText(text('先检查源文件，再创建模型。输入检查和计算为异步提交，请查看 Job Monitor。'))

    def tab(self,tabs,label):
        FXTabItem(tabs,text(label))
        return FXVerticalFrame(tabs,opts=FRAME_RAISED|LAYOUT_FILL_X|LAYOUT_FILL_Y)

    def processUpdates(self):
        for panel in (self.patch_panel,self.film_panel):
            if self.form.kw['analysis_mode'].getValue()==1: panel.enable()
            else: panel.disable()

    def field(self,parent,key,label):
        return AFXTextField(parent,28,text(label+': '),self.form.kw[key],0)

    def combo(self,parent,key,label,items):
        combo=AFXComboBox(parent,28,len(items),text(label+': '),self.form.kw[key],0)
        for i,item in enumerate(items):
            combo.appendItem(item,int(item) if key=='load_axis' else 0)
        return combo

    def file_row(self,parent,key,label,pattern):
        row=FXHorizontalFrame(parent,opts=LAYOUT_FILL_X)
        AFXTextField(row,52,text(label+': '),self.form.kw[key],0)
        picker=FilePicker(self.form.kw[key],pattern); self.pickers.append(picker)
        FXButton(row,'...',None,picker,AFXMode.ID_ACTIVATE)

    def call(self,action):
        try:
            cfg=self.form.settings()
            cfg['state_selection']='auto'
            self.form.action.setValue(action)
            self.form.overrides.setValue(json.dumps(cfg,ensure_ascii=True))
            # Inputs have already been loaded into the GUI, so do not read an unrelated path again.
            command='cai_kernel.execute(action=%r, overrides_json=%r)' % (action,json.dumps(cfg,ensure_ascii=True))
            sendCommand(command)
            self.status.setText(text('命令已发送：'+action+'。请查看消息区 / Job Monitor；提取完成后点“刷新报告”。'))
        except Exception as exc:
            showAFXErrorDialog(self,text(str(exc)))
        return 1

    def inspect(self,*args): return self.call('inspect')
    def build(self,*args): return self.call('build')
    def check(self,*args): return self.call('datacheck')
    def submit(self,*args): return self.call('submit')
    def results(self,*args): return self.call('results')

    def report(self,*args):
        try:
            cfg=self.form.settings()
            path=os.path.join(cfg['output_dir'],cfg['job_name']+'_result.json')
            with open(path,'rb') as f: r=json.loads(f.read().decode('utf-8'))
            lines=['Peak load: %.6g kN' % (r['peak_force_N']/1000.),
                   'Observed nominal peak: %.6g MPa' % r['observed_nominal_peak_MPa'],
                   'Qualified CAI strength: %s MPa' % r['cai_strength_MPa']]
            lines.extend(r['warnings'])
            self.status.setText(text('\n'.join(lines)))
        except Exception as exc: showAFXErrorDialog(self,text(str(exc)))
        return 1

    def load_config(self,*args):
        try:
            cfg=load(self.form.config_path.getValue())
            cfg['state_selection']='auto'
            for key,val in cfg.items(): self.form.kw[key].setValue(val)
            self.status.setText(text('配置已载入。'))
        except Exception as exc: showAFXErrorDialog(self,text(str(exc)))
        return 1

    def save_config(self,*args):
        try:
            cfg=self.form.settings()
            cfg['state_selection']='auto'
            path=self.form.config_path.getValue()
            if not path:
                if not os.path.isdir(cfg['output_dir']): os.makedirs(cfg['output_dir'])
                path=os.path.join(cfg['output_dir'],cfg['job_name']+'_settings.json')
                self.form.config_path.setValue(path)
            dump(path,cfg); self.status.setText(text('配置已保存：'+path))
        except Exception as exc: showAFXErrorDialog(self,text(str(exc)))
        return 1

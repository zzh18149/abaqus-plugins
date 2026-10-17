#-*- coding:utf-8 -*-
from abaqusGui import *
import csv
import json
import locale
import os
###########################################################################
# Class definition
###########################################################################
thisPath = os.path.abspath(__file__)
thisDir = os.path.dirname(thisPath)

def TEXT(s = "测试"):
    """AFX in Abaqus 2024 accepts Python 3 Unicode strings."""
    value = s.decode('utf-8') if isinstance(s, bytes) else str(s)
    # Windows native wrappers use the C character locale for Unicode input.
    # Set only LC_CTYPE; preserve numerical/decimal and other locale settings.
    if os.name == 'nt' and not value.isascii():
        locale.setlocale(locale.LC_CTYPE, '.UTF8')
    return value
  

class TestDB(AFXDataDialog):
    [
        ID_CLICKED_CREATE_MODEL,
        ID_CLICKED_UPDATE_MATERIAL,
        ID_CLICKED_UPDATE_MODEL,
        ID_CLICKED_SELECT_MATRIAL,
        ID_CLICKED_PARSEODB,
        ID_CLICKED_UPDATE_BC,
        ID_LOAD_CSV,
        ID_DATA_PREVIEW,
        ID_CLICKED_SUBMIT,
        ID_MODIFY_PATCH,
        ID_MODIFY_STAIR,
        ID_MODIFY_SCARF,
        ID_OPEN_RESULT_FOLDER,
        ID_EXPORT_RESULT_SUMMARY,
        ID_CLICKED_MESH_MODEL,
    ] = range(AFXDataDialog.ID_LAST, AFXDataDialog.ID_LAST + 15)
    def __init__(self, form):
        AFXDataDialog.__init__(
          self, form, 'Composite Repair Strength Analysis V2.2.0',
          self.OK | self.APPLY | self.CANCEL,
          w=920, h=680)
        ##
        self.form = form
        ###
        self.dataDict = {}
        self.resultRecords = []
        self.lastResultDirectory = None

        #functions

        FXMAPFUNC(self, SEL_COMMAND, self.ID_CLICKED_CREATE_MODEL,TestDB.omCmdSelectCreateModel)        ## 创建模型
        FXMAPFUNC(self, SEL_COMMAND, self.ID_LOAD_CSV,TestDB.omCmdLoadCSV) #加载csv
        FXMAPFUNC(self, SEL_COMMAND, self.ID_DATA_PREVIEW,TestDB.omCmdDataPreview) #数据预览
        FXMAPFUNC(self, SEL_COMMAND, self.ID_CLICKED_UPDATE_MODEL,TestDB.omCmdUpdateModel)#更新模型
        FXMAPFUNC(self, SEL_COMMAND, self.ID_CLICKED_UPDATE_MATERIAL,TestDB.omCmdUpdateMaterial)#更新模型
        FXMAPFUNC(self, SEL_COMMAND, self.ID_CLICKED_PARSEODB,TestDB.omCmdParseODB)
        FXMAPFUNC(self, SEL_COMMAND, self.ID_OPEN_RESULT_FOLDER,
                  TestDB.omCmdOpenResultFolder)
        FXMAPFUNC(self, SEL_COMMAND, self.ID_EXPORT_RESULT_SUMMARY,
                  TestDB.omCmdExportResultSummary)
        FXMAPFUNC(self, SEL_COMMAND, self.ID_CLICKED_UPDATE_BC,TestDB.omCmdUpdateBC)
        FXMAPFUNC(self, SEL_COMMAND, self.ID_CLICKED_SUBMIT,TestDB.omCmdSelectSubmit)
        FXMAPFUNC(self, SEL_COMMAND, self.ID_CLICKED_MESH_MODEL,
                  TestDB.omCmdMeshModel)
        FXMAPFUNC(self, SEL_COMMAND, self.ID_MODIFY_PATCH,
                  TestDB.onSelectPatch)
        FXMAPFUNC(self, SEL_COMMAND, self.ID_MODIFY_STAIR,
                  TestDB.onSelectStair)
        FXMAPFUNC(self, SEL_COMMAND, self.ID_MODIFY_SCARF,
                  TestDB.onSelectScarf)
        ###
        self.form.pluginDir.setValue(thisDir)
        self.form.mSubroutineFileKw.setValue(
            os.path.join(thisDir, "scripts", "hashinDel.for"))
        # FXMAPFUNC(self, SEL_COMMAND, self.ID_CLICKED_AUTOMATIC, TestDB.omCmdSelectAutomatic)
        ###
        ###################
        ### First page  ###
        length = 12
        ###################
        tabBook1 = FXTabBook(self, None, 0, LAYOUT_FILL_X|LAYOUT_FILL_Y)
        FXTabItem(tabBook1, TEXT("模型参数设置"))
        #                                                               x  y  w  h  pl pr pt pb
        tab1Frame = FXVerticalFrame(tabBook1, FRAME_RAISED | FRAME_SUNKEN, 0, 0, 0, 0, 4, 10, 7, 5)
        # tabBook2 = FXTabBook(tab1Frame, None, 0, LAYOUT_FILL_X)
        # For modeling dimensionality
        
        
        #########第一个页面
        # 创建一个 GroupBox，标题为 a
        GroupBox_a = FXGroupBox(p=tab1Frame, text=TEXT("模型参数设置"),opts=FRAME_GROOVE|LAYOUT_FILL_X)
        #
        row1 = FXHorizontalFrame(GroupBox_a)
        aligner = AFXVerticalAligner(row1, pl=0, pr=0, pt=0, pb=0)
        AFXTextField(aligner, length, TEXT("长度(mm):"),form.mLength)
        AFXTextField(aligner,length, TEXT("损伤直径(mm):"),form.mPitDiameter)
        ########
        aligner = AFXVerticalAligner(row1, pl=0, pr=0, pt=0, pb=0)
        AFXTextField(aligner, length, TEXT("宽度(mm):"),form.mWidth)
        AFXTextField(aligner,length, TEXT("原板铺层数量:"),form.mNumLayer)
        #
        aligner = AFXVerticalAligner(row1, pl=0, pr=0, pt=0, pb=0)
        AFXTextField(aligner, length, TEXT("总厚度(mm):"),form.mHeight)
        #
        aligner = AFXVerticalAligner(row1, pl=0, pr=0, pt=0, pb=0)
        # AFXTextField(aligner, length, labelText=TEXT("长度sss:"))
       
        #
        aligner = AFXVerticalAligner(GroupBox_a, pl=0, pr=0, pt=0, pb=0)
        AFXTextField(aligner, 88, TEXT("铺层角度："),form.mLayerAngle)
        FXLabel(
            GroupBox_a,
            TEXT("单层厚度由“总厚度/铺层数量”自动计算；原板层间不建立实体胶层。"),
            opts=LABEL_NORMAL)
        ####
        # FXLabel(aligner, TEXT("修补参数:"), ic=None, opts=LABEL_NORMAL, x=0, y=0, w=0, h=0, pl=DEFAULT_PAD, pr=DEFAULT_PAD, pt=DEFAULT_PAD, pb=DEFAULT_PAD)
        
        GroupBox_c = FXGroupBox(
            tab1Frame, text=TEXT("修补参数设置"),
            opts=FRAME_GROOVE | LAYOUT_FILL_X)
        #
        row1 = FXHorizontalFrame(GroupBox_c)
        FXLabel(row1, TEXT("选择修补类型:"), ic=None, opts=LABEL_NORMAL, x=0, y=0, w=0, h=0, pl=DEFAULT_PAD, pr=DEFAULT_PAD, pt=DEFAULT_PAD, pb=DEFAULT_PAD)
        #
        
        
        self.parameterPages = FXSwitcher(
            GroupBox_c, LAYOUT_FILL_X)

        self.modifyPatchButton = FXRadioButton(
            row1, TEXT('贴补式'), self, self.ID_MODIFY_PATCH,
            LAYOUT_SIDE_LEFT | RADIOBUTTON_NORMAL,
            0, 0, 0, 0, 6, 0, 3, 5)
        self.modifyStairButton = FXRadioButton(
            row1, TEXT('阶梯式'), self, self.ID_MODIFY_STAIR,
            LAYOUT_SIDE_LEFT | RADIOBUTTON_NORMAL,
            0, 0, 0, 0, 100, 0, 3, 5)
        self.modifyScarfButton = FXRadioButton(
            row1, TEXT('斜接式'), self, self.ID_MODIFY_SCARF,
            LAYOUT_SIDE_LEFT | RADIOBUTTON_NORMAL,
            0, 0, 0, 0, 85, 0, 3, 5)
        self.selectedModifyType = 1
        self.modifyStairButton.setCheck(True)
        self.parameterPages.setCurrent(1)
        self.form.modifyType.setValue(1)
        #############
        # 创建修补参数 TabBook（先不添加Tab项，动态添加）
        # 创建三个独立的 GroupBox，分别放置三种修补参数
        # ========== 贴补参数 GroupBox ==========
        self.tb_group = FXGroupBox(self.parameterPages, text=TEXT("贴补参数"),
                                opts=FRAME_GROOVE | LAYOUT_FILL_X)
        tb_aligner = AFXVerticalAligner(self.tb_group, pl=0, pr=0, pt=0, pb=0)

        row_tb1 = FXHorizontalFrame(tb_aligner, LAYOUT_FILL_X)
        
        ###
        # 贴补类型 Radio 按钮组
        FXLabel(row_tb1, TEXT("贴补类型:"), None, LAYOUT_CENTER_Y, pl=0, pr=10)
        self.tb_type_sw = FXSwitcher(row_tb1)
        self.tb_type_double = FXRadioButton(row_tb1, TEXT("双面贴补"), self.tb_type_sw, 
                                                FXSwitcher.ID_OPEN_FIRST, LAYOUT_SIDE_LEFT | RADIOBUTTON_NORMAL, pl=0, pr=10)
        # self.tb_type_single = FXRadioButton(row_tb1, TEXT("单面贴补"), self.tb_type_sw, 
        #                                         FXSwitcher.ID_OPEN_FIRST+1, LAYOUT_SIDE_LEFT | RADIOBUTTON_NORMAL, pl=0, pr=10)
    
        self.tb_type_sw.setCurrent(0)  # 当前固定为双面贴补
        ##
        FXLabel(row_tb1, TEXT("贴补形状:"), None, LAYOUT_CENTER_Y, pl=0, pr=10)
        self.tb_shape_sw = FXSwitcher(row_tb1)
        self.tb_shape_circle = FXRadioButton(row_tb1, TEXT("圆形贴补"), self.tb_shape_sw, 
                                                FXSwitcher.ID_OPEN_FIRST, LAYOUT_SIDE_LEFT | RADIOBUTTON_NORMAL, pl=0, pr=10)
        # self.tb_shape_rectangle = FXRadioButton(row_tb1, TEXT("矩形贴补"), self.tb_shape_sw, 
        #                                         FXSwitcher.ID_OPEN_FIRST + 1, LAYOUT_SIDE_LEFT | RADIOBUTTON_NORMAL, pl=0, pr=10)
        self.tb_shape_sw.setCurrent(0)  # 当前固定为圆形贴补

        row_tb1 = FXHorizontalFrame(tb_aligner, LAYOUT_FILL_X)
        


        #########

        
        AFXTextField(row_tb1, 10, TEXT("铺层数量:"), self.form.tbLayerNum,
                    opts=AFXTEXTFIELD_INTEGER | LAYOUT_CENTER_Y)
        AFXTextField(row_tb1, 10, TEXT("单侧实体胶层厚度(mm):"), self.form.glueThickness,
                    opts=AFXTEXTFIELD_FLOAT | LAYOUT_CENTER_Y)
        
        self.tbWidth = AFXTextField(row_tb1, 10, TEXT("补片直径(mm):"), self.form.tbWidth,
                    opts=AFXTEXTFIELD_FLOAT | LAYOUT_CENTER_Y)
        self.tbHeight = AFXTextField(row_tb1, 10, TEXT("备用尺寸(mm):"), self.form.tbHeight,
                    opts=AFXTEXTFIELD_FLOAT | LAYOUT_CENTER_Y)

        row_tb2 = FXHorizontalFrame(tb_aligner, LAYOUT_FILL_X)
        AFXTextField(row_tb2, 60, TEXT("总铺层角度(AUTO=按原板上下表面生成):"), self.form.tbLayerAngle,
                    opts=AFXTEXTFIELD_STRING | LAYOUT_CENTER_Y)
        FXLabel(
            tb_aligner,
            TEXT("当前贴补模式：中心贯穿圆孔+上下圆形补片；总铺层数自动均分，"
                 "上下各设一层线弹性实体胶层并采用Tie，不计算胶层失效。"),
            opts=LABEL_NORMAL | LAYOUT_LEFT)

        # ========== 阶梯参数 GroupBox ==========
        self.jt_group = FXGroupBox(self.parameterPages, text=TEXT("阶梯参数"),
                                opts=FRAME_GROOVE | LAYOUT_FILL_X)
        jt_aligner = AFXVerticalAligner(self.jt_group, pl=0, pr=0, pt=0, pb=0)

        row_jt1 = FXHorizontalFrame(jt_aligner, LAYOUT_FILL_X)
        AFXTextField(row_jt1, 10, TEXT("阶梯数量:"), self.form.jtNum,
                    opts=AFXTEXTFIELD_INTEGER | LAYOUT_CENTER_Y)
        AFXTextField(row_jt1, 10, TEXT("最外直径(mm):"), self.form.repairOuterDiameter,
                    opts=AFXTEXTFIELD_FLOAT | LAYOUT_CENTER_Y)
        AFXTextField(row_jt1, 10, TEXT("补片铺层数:"), self.form.tbLayerNum,
                    opts=AFXTEXTFIELD_INTEGER | LAYOUT_CENTER_Y)
        AFXTextField(row_jt1, 10, TEXT("实体胶层厚度(mm):"), self.form.glueThickness,
                    opts=AFXTEXTFIELD_FLOAT | LAYOUT_CENTER_Y)
        row_jt2 = FXHorizontalFrame(jt_aligner, LAYOUT_FILL_X)
        AFXTextField(
            row_jt2, 60, TEXT("补片铺层角度(AUTO=同原板):"),
            self.form.tbLayerAngle,
            opts=AFXTEXTFIELD_STRING | LAYOUT_CENTER_Y)
        FXLabel(
            jt_aligner,
            TEXT("当前阶梯模式：线弹性实体胶层+两侧Tie；补片允许高出胶层厚度，不计算胶层失效。"),
            opts=LABEL_NORMAL | LAYOUT_LEFT)

        # ========== 斜接参数 GroupBox ==========
        self.xj_group = FXGroupBox(self.parameterPages, text=TEXT("斜接参数"),
                                opts=FRAME_GROOVE | LAYOUT_FILL_X)
        xj_aligner = AFXVerticalAligner(self.xj_group, pl=0, pr=0, pt=0, pb=0)

        row_xj1 = FXHorizontalFrame(xj_aligner, LAYOUT_FILL_X)
        AFXTextField(row_xj1, 10, TEXT("斜接角度(°):"), self.form.xjAngle,
                    opts=AFXTEXTFIELD_FLOAT | LAYOUT_CENTER_Y)
        AFXTextField(row_xj1, 10, TEXT("补片铺层数:"), self.form.tbLayerNum,
                    opts=AFXTEXTFIELD_INTEGER | LAYOUT_CENTER_Y)
        AFXTextField(row_xj1, 10, TEXT("实体胶层厚度(mm):"), self.form.glueThickness,
                    opts=AFXTEXTFIELD_FLOAT | LAYOUT_CENTER_Y)
        row_xj2 = FXHorizontalFrame(xj_aligner, LAYOUT_FILL_X)
        AFXTextField(
            row_xj2, 60, TEXT("补片铺层角度(AUTO=同原板):"),
            self.form.tbLayerAngle,
            opts=AFXTEXTFIELD_STRING | LAYOUT_CENTER_Y)
        FXLabel(
            xj_aligner,
            TEXT("当前斜接模式：连续斜面+线弹性实体胶层+两侧Tie，不计算胶层失效。"),
            opts=LABEL_NORMAL | LAYOUT_LEFT)

        # 初始隐藏阶梯和斜接，只显示贴补
        # self.jt_group.hide()
        # self.xj_group.hide()

        # FXButton(p=self, text='Create Model',
        #  tgt=self.form.cmd_create, sel=AFXMode.ID_ACTIVATE)
        GroupBox_b = FXGroupBox(p=tab1Frame, text=TEXT("材料参数设置"),opts=FRAME_GROOVE|LAYOUT_FILL_X)
        #
        row1 = FXHorizontalFrame(GroupBox_b)
        aligner = AFXVerticalAligner(row1, pl=0, pr=0, pt=0, pb=0)
        
        # 2. 文本输入框
        #File Selector
        fileHandler = FileDBFileHandler(form, 'mMaterialFile', ' (*.json)',TEXT("选择材料数据文件"))
        File_Text = AFXTextField(p=row1, ncols=56, labelText=TEXT('材料json文件:'), tgt=form.mMaterialFileKw, sel=0,
            opts=AFXTEXTFIELD_STRING|LAYOUT_CENTER_Y)
        icon = afxGetIcon('fileOpen', AFX_ICON_SMALL )
        FXButton(p=row1, text='	Select File\nFrom Dialog', ic=icon, tgt=fileHandler, sel=AFXMode.ID_ACTIVATE,
            opts=BUTTON_NORMAL|LAYOUT_CENTER_Y, x=0, y=0, w=0, h=0, pl=1, pr=1, pt=1, pb=1)
        ######
        FXButton(
            p=row1,
            text=TEXT('加载材料参数'),
            tgt=self,
            sel=self.ID_DATA_PREVIEW,
            opts=BUTTON_NORMAL|LAYOUT_CENTER_Y
        )

   
    #####################
     # 创建主布局
        group_box = FXGroupBox(tab1Frame, TEXT("材料参数汇总"), FRAME_GROOVE | LAYOUT_FILL_X )
        
        # 创建文本显示区域（放在 GroupBox 内）
        self.text_area = FXText(group_box, None, 0, LAYOUT_FILL_X)
        self.text_area.setEditable(True)
        defaultMaterial = os.path.join(
            thisDir, "material", "material_template_t300_5208.json")
        if os.path.isfile(defaultMaterial):
            self.form.mMaterialFileKw.setValue(defaultMaterial)
            with open(defaultMaterial, "r", encoding="utf-8-sig") as materialFile:
                materialText = materialFile.read()
            materialCompact = json.dumps(
                json.loads(materialText), separators=(',', ':'))
            self.text_area.setText(materialCompact)
            self.form.matParaDict.setValue(materialCompact)
    
    #####################

            
        # 创建一个水平容器
        #  tabBook1
        button_row = FXHorizontalFrame(tab1Frame, LAYOUT_FILL_X, 
                                        x=0, y=0, w=0, h=0, 
                                        pl=10, pr=10, pt=5, pb=5)

        # 模型建立按钮。阶梯/贴补仍一次建立完整有限元模型；
        # 真正连续斜接式分为“几何/分区”和“网格/分析”两步。
        self.createModelButton = FXButton(
            button_row, TEXT("创建完整有限元模型"), None,
            self, self.ID_CLICKED_CREATE_MODEL,
            opts=BUTTON_NORMAL | LAYOUT_CENTER_X,
            x=0, y=0, w=0, h=0, pl=10, pr=10)

        self.meshModelButton = FXButton(
            button_row, TEXT("划分网格并建立分析"), None,
            self, self.ID_CLICKED_MESH_MODEL,
            opts=BUTTON_NORMAL | LAYOUT_CENTER_X,
            x=0, y=0, w=0, h=0, pl=10, pr=10)
        self.meshModelButton.hide()

        FXButton(
            button_row, TEXT("更新几何模型"), None,
            self, self.ID_CLICKED_UPDATE_MODEL,
            opts=BUTTON_NORMAL | LAYOUT_CENTER_X,
            x=0, y=0, w=0, h=0, pl=10, pr=10)

        FXButton(
            button_row, TEXT("更新材料参数"), None,
            self, self.ID_CLICKED_UPDATE_MATERIAL,
            opts=BUTTON_NORMAL | LAYOUT_CENTER_X,
            x=0, y=0, w=0, h=0, pl=10, pr=10)

        meshGroup = FXGroupBox(
            tab1Frame, text=TEXT("模型网格设置"),
            opts=FRAME_GROOVE | LAYOUT_FILL_X)
        meshRow = FXHorizontalFrame(meshGroup, LAYOUT_FILL_X)
        AFXTextField(
            meshRow, 8,
            labelText=TEXT("网格等级(0审计/1标准/2精细):"),
            tgt=form.meshLevel)
        FXLabel(
            meshRow,
            TEXT("该参数在创建完整模型或划分网格时读取；"
                 "模型生成后再修改不会自动重划网格。"),
            opts=LABEL_NORMAL | LAYOUT_CENTER_Y)

        # GroupBox_b = FXGroupBox(p=tab1Frame, text=TEXT("材料参数预览"),opts=FRAME_GROOVE|LAYOUT_FILL_X)
        #
        # row1 = FXHorizontalFrame(GroupBox_b)
        # aligner = AFXVerticalAligner(row1, pl=0, pr=0, pt=0, pb=0)
        # mat_preview = FXText(GroupBox_b, tgt=None,  opts=LAYOUT_FILL_X,x=0, y=0, h=120)
        # mat_preview.appendText(TEXT("材料参数预览"),len(TEXT("材料参数预览")))


        ###########################################
        ###################
        ### Second page ###
        ###################
         # 创建标签页

        
        ##########################边界条件
        FXTabItem(tabBook1, TEXT('边界条件和求解设置'))
        #                                                              x  y  w  h  pl pr pt pb
        tab2Frame = FXVerticalFrame(tabBook1, FRAME_RAISED | FRAME_SUNKEN, 0, 0, 0, 0, 4, 10, -7, 5)
        # 创建一个 GroupBox，标题为 a
        GroupBox_a = FXGroupBox(tab2Frame, text=TEXT("边界条件设置"),opts=FRAME_GROOVE|LAYOUT_FILL_X)
        #
        row1 = FXHorizontalFrame(GroupBox_a)
        aligner = AFXVerticalAligner(row1, pl=0, pr=0, pt=0, pb=0)
        input_row = FXHorizontalFrame(row1, LAYOUT_FILL_X, 
                              x=0, y=0, w=0, h=0,
                              pl=10, pr=10, pt=5, pb=5)
        # 
        AFXTextField(input_row, 12, TEXT("轴向位移值(mm):"),tgt = form.disValue)
        FXLabel(
            input_row,
            TEXT("沿板长方向拉伸；右端面全部节点直接施加相同轴向位移。"),
            opts=LABEL_NORMAL | LAYOUT_CENTER_Y)
        
        ###########
        self.compressBc  = FXCheckButton(
        input_row,                          # 父窗口
        TEXT("压缩(默认是拉伸)"),                  # 标签文
            )
        #
        self.compressBc.hide()
        #
                
        # #
        # button_row = FXHorizontalFrame(tab2Frame, LAYOUT_FILL_X, 
        #                                 x=0, y=0, w=0, h=0, 
        #                                 pl=10, pr=10, pt=5, pb=5)

        # # 在水平容器中添加按钮
        # FXButton(button_row, TEXT("创建几何模型"), None, self, self.ID_CLICKED_CREATE_MODEL,
        #         opts=BUTTON_NORMAL | LAYOUT_CENTER_X,
        #         x=0, y=0, w=0, h=0, pl=10, pr=10)

        # FXButton(button_row, TEXT("更新几何模型"), None, self, self.ID_CLICKED_UPDATE_MODEL,
        #         opts=BUTTON_NORMAL | LAYOUT_CENTER_X,
        #         x=0, y=0, w=0, h=0, pl=10, pr=10)
        
 
        FXButton(input_row, TEXT("更新边界条件与求解设置"), None, self, self.ID_CLICKED_UPDATE_BC,
                opts=BUTTON_NORMAL | LAYOUT_CENTER_X,
                x=0, y=0, w=0, h=0, pl=10, pr=10)
     
        FXLabel(
            GroupBox_a,
            TEXT("该按钮更新已建模型中的位移、分析时间、目标时间增量和输出间隔；"
                 "Job名称、CPU和自动续算参数在提交时读取。提交计算时也会自动同步。"
                 "底部“确定/应用”不是模型更新按钮。"),
            opts=LABEL_NORMAL | LAYOUT_LEFT)
        ############

                #
        GroupBox_a = FXGroupBox(tab2Frame, text=TEXT("求解设置"),opts=FRAME_GROOVE|LAYOUT_FILL_X)
        #
        container = FXVerticalFrame(GroupBox_a)
        row1 = FXHorizontalFrame(container)
        #aligner = AFXVerticalAligner(row1, pl=0, pr=0, pt=0, pb=0)
        kd_bp_input= AFXTextField(row1, length, labelText=TEXT("Job名称:"),tgt=form.jobName,x=0,y=0,w=0,h=0,pl=20,pr=50)
        kd_bp_input= AFXTextField(row1, length, labelText=TEXT("CPU数量:"),tgt = form.numOfCpus,x=0,y=0,w=0,h=0,pl=20,pr=20)
        rowSettings2 = FXHorizontalFrame(container)
        AFXTextField(rowSettings2, length, labelText=TEXT("分析时间(s):"),
                     tgt=form.stepTime)
        AFXTextField(rowSettings2, length, labelText=TEXT("目标时间增量(s):"),
                     tgt=form.targetTimeIncrement)

        autoRow1 = FXHorizontalFrame(container, LAYOUT_FILL_X)
        self.autoSolveCheck = FXCheckButton(
            autoRow1,
            TEXT("自动求剩余强度（未出现持续峰后下降时自动Restart续算）"),
            tgt=form.autoSolve)

        autoRow2 = FXHorizontalFrame(container, LAYOUT_FILL_X)
        AFXTextField(
            autoRow2, length, labelText=TEXT("每段续算位移(mm):"),
            tgt=form.autoIncrementDisplacement)
        AFXTextField(
            autoRow2, length, labelText=TEXT("最大允许位移(mm):"),
            tgt=form.autoMaximumDisplacement)
        AFXTextField(
            autoRow2, length, labelText=TEXT("峰后下降比例:"),
            tgt=form.peakDropRatio)
        AFXTextField(
            autoRow2, length, labelText=TEXT("连续峰后帧数:"),
            tgt=form.minimumPostPeakFrames)
        FXLabel(
            container,
            TEXT("自动模式保持初始位移/时间对应的加载速率；达到峰值后连续下降判据即停止。"),
            opts=LABEL_NORMAL | LAYOUT_LEFT)
        ################################
        row2 = FXHorizontalFrame(container)
                        #File Selector
        fileHandler = FileDBFileHandler(form, 'mSubroutineFile', ' (*.for)',TEXT("选择Fortran子程序文件"))
        File_Text = AFXTextField(p=row2, ncols=56, labelText=TEXT('子程序Fortran文件:'), tgt=form.mSubroutineFileKw, sel=0,
            opts=AFXTEXTFIELD_STRING|LAYOUT_CENTER_Y)
        icon = afxGetIcon('fileOpen', AFX_ICON_SMALL )
        FXButton(p=row2, text='	Select File\nFrom Dialog', ic=icon, tgt=fileHandler, sel=AFXMode.ID_ACTIVATE,
            opts=BUTTON_NORMAL|LAYOUT_CENTER_Y, x=0, y=0, w=0, h=0, pl=1, pr=1, pt=1, pb=1)
        
        

        
        
        vf = FXVerticalFrame(tab2Frame, 0, 0, 0, 0, 0, 12, 10, 10, 10)
        va = AFXVerticalAligner(tab2Frame)
        vh = FXHorizontalFrame(va)
        
        # FXButton(vh, TEXT("创建模型"),None, self, self.ID_CLICKED_MANUAL,x=0, y=0, w=0, h=0,pl=20,pr=20)
        self.submitButton = FXButton(
            vh, TEXT("提交计算 / 自动求剩余强度"), None, self, self.ID_CLICKED_SUBMIT,
            x=0, y=0, w=0, h=0, pl=20, pr=20)
        #######
        
        
        
        
        ###########################
        
        
        
        
        #结果page 页面
        FXTabItem(tabBook1, TEXT('结果报告'))
        #                                                              x  y  w  h  pl pr pt pb
        tab2Frame = FXVerticalFrame(tabBook1, FRAME_RAISED | FRAME_SUNKEN, 0, 0, 0, 0, 4, 10, -7, 5)
        GroupBox_a = FXGroupBox(tab2Frame, text=TEXT("ODB自动结果报告"),opts=FRAME_GROOVE|LAYOUT_FILL_X)
        #
        row1 = FXVerticalFrame(GroupBox_a)
        aligner = FXHorizontalFrame(row1, pl=0, pr=0, pt=0, pb=0,opts=LAYOUT_FILL_X)
        
        # 2. 文本输入框
        fileHandler = FileDBFileHandler(form, 'mOdbFile', ' (*.odb)',TEXT("选择结果ODB文件"))
        File_Text = AFXTextField(p=aligner, ncols=46, labelText=TEXT('结果ODB文件:'), tgt=form.mOdbFileKw, sel=0,
            opts=AFXTEXTFIELD_STRING|LAYOUT_CENTER_Y,pl=30)
        icon = afxGetIcon('fileOpen', AFX_ICON_SMALL )
        FXButton(p=aligner, text='	Select File\nFrom Dialog', ic=icon, tgt=fileHandler, sel=AFXMode.ID_ACTIVATE,
            opts=BUTTON_NORMAL|LAYOUT_FILL_X|LAYOUT_CENTER_Y)
        
                
        FXButton(
            p=aligner,
            text=TEXT('生成结果报告'),
            tgt=self,
            sel=self.ID_CLICKED_PARSEODB,
            opts=BUTTON_NORMAL|LAYOUT_CENTER_Y
        )
        
        
        #############
        #########
        aligner = FXHorizontalFrame(row1, pl=0, pr=0, pt=0, pb=0)
        sw2 = FXSwitcher(aligner)
        FXLabel(aligner, TEXT("结果类型:"),x=0,y=0,w=0,h=0,pt=2)
        rdb_stiffness = FXRadioButton(aligner,TEXT('最大名义应力(MPa)'), sw2, FXSwitcher.ID_OPEN_FIRST, LAYOUT_SIDE_LEFT|RADIOBUTTON_NORMAL,0, 0, 0, 0, 6, 0, 2, 5)
        # rdb_risk = FXRadioButton(aligner,TEXT('屈曲载荷'), sw2,FXSwitcher.ID_OPEN_FIRST+1, LAYOUT_SIDE_LEFT|RADIOBUTTON_NORMAL,0, 0, 0, 0, 50, 50,2, 5)
        
        # self.XP_btn = FXButton(aligner, TEXT('计算'),None, self, self.ID_CLICKED_MANUAL,x=0, y=0, w=0, h=0,pl=20,pr=20)
        
                                     

         # 详细结果表。第0列为AFXTable的行号列，1～13列为结果数据。
        GroupBox_a = FXGroupBox(
            tab2Frame, text=TEXT("结果显示"),
            opts=FRAME_GROOVE | LAYOUT_FILL_X | LAYOUT_FILL_Y)
        resultTableFrame = FXVerticalFrame(
            GroupBox_a, LAYOUT_FILL_X | LAYOUT_FILL_Y)
        table = AFXTable(
            resultTableFrame, 1, 14, 1, 14, None, 0,
            AFXTABLE_EDITABLE | LAYOUT_FILL_X | LAYOUT_FILL_Y)
        table.setPopupOptions(
            AFXTable.POPUP_CUT | AFXTable.POPUP_COPY |
            AFXTable.POPUP_DELETE_ROW |
            AFXTable.POPUP_CLEAR_CONTENTS |
            AFXTable.POPUP_WRITE_TO_FILE)
        table.setLeadingRows(1)
        table.setLeadingColumns(1)

        resultColumnWidths = (
            210, 100, 100, 115, 100, 115, 110,
            90, 90, 90, 100, 90, 90)
        for columnIndex, columnWidth in enumerate(
                resultColumnWidths, start=1):
            table.setColumnWidth(columnIndex, columnWidth)
            table.setColumnType(columnIndex, AFXTable.TEXT)

        table.setLeadingRowLabels(TEXT(
            "算例名称\t峰值载荷(kN)\t峰值位移(mm)\t"
            "剩余强度(MPa)\t峰后下降(%)\t首损伤模式\t"
            "首损伤载荷(kN)\tKE/IE(%)\tAE/IE(%)\t"
            "VD/IE(%)\t平衡误差(%)\t删除单元\t有效性"))
        table.setStretchableColumn(1)
        table.showHorizontalGrid(True)
        table.showVerticalGrid(True)

        resultButtonRow = FXHorizontalFrame(
            resultTableFrame, LAYOUT_FILL_X)
        FXButton(
            resultButtonRow, TEXT("打开结果文件夹"), None,
            self, self.ID_OPEN_RESULT_FOLDER,
            opts=BUTTON_NORMAL | LAYOUT_CENTER_Y,
            pl=12, pr=12)
        FXButton(
            resultButtonRow, TEXT("导出当前汇总CSV"), None,
            self, self.ID_EXPORT_RESULT_SUMMARY,
            opts=BUTTON_NORMAL | LAYOUT_CENTER_Y,
            pl=12, pr=12)
        FXLabel(
            resultButtonRow,
            TEXT("表格可横向滚动；每次后处理会追加一行。"),
            opts=LABEL_NORMAL | LAYOUT_CENTER_Y)

        self.table = table
        ################################################
        #
        self.form = form
        #########
        self.sw1 = self.parameterPages
        self.sw2 = sw2
        self.modifyType = form.modifyType #修补类型
        
   
        
        # self.r_hd_jc_input = hd_jc_input #胶层厚度
        # self.r_num_jt_input = num_jt_input #阶梯-数目
        # self.r_jd_jt_input = jd_jt_input #阶梯-角度
        
        # #
        # self.r_num_bp_input = num_bp_input #补片-数量
        # self.r_hd_bp_input = hd_bp_input # 补片-厚度
        
        #########后处理
        self.parseOdbType = form.parseOdbType
        
        ########
        self.isFirst = True
        self.dataPreviewDB = None
        return
    
    def getMatParams(self):
        jsonData = self.text_area.getText()
        self.form.matParaDict.setValue(jsonData)
        
        return
    
    
    def omCmdUpdateBC(self, sender, sel, ptr):
        self.getMatParams()
        self.form.cmdType.setValue("updateBC")
        self.form.issueCommands()
        self.form.showMessage(
            TEXT("已发送更新命令：位移、分析时间、目标时间增量和输出间隔"
                 "将同步到当前Model-1；提交时还会再次自动同步。"))
        return
    
    
    
    def omCmdUpdateModel(self, sender, sel, ptr):
        self.getMatParams()
        self.form.cmdType.setValue("updateModel")
        self.form.issueCommands() 
        return
    
    def omCmdUpdateMaterial(self, sender, sel, ptr):
        self.getMatParams()
        self.form.cmdType.setValue("updateMaterial")
        self.form.issueCommands() 
        return
    ##加载csv文件
    def omCmdLoadCSV(self, sender, sel, ptr):
        return
    def omCmdDataPreview(self, sender, sel, ptr):
        jsonFile = self.form.mMaterialFileKw.getValue()
        self.form.showMessage(jsonFile)
        if not jsonFile or not os.path.isfile(jsonFile):
            raise ValueError(TEXT("请选择存在的材料 JSON 文件"))
        with open(jsonFile,'r',encoding='utf-8-sig') as f:
            matDataString = f.read()
        matString_compact = json.dumps(json.loads(matDataString), separators=(',', ':'))

        self.text_area.setText(matString_compact)
        return
    
        
    
    #####解析odb结果

    def _resultNumber(self, value, default=None):
        try:
            if value is None:
                return default
            return float(value)
        except Exception:
            return default

    def _resultText(self, value, digits=3, suffix=""):
        number = self._resultNumber(value)
        if number is None:
            return "--"
        return ("%." + str(digits) + "f%s") % (number, suffix)

    def _damageModeText(self, mode):
        mapping = {
            "fiber tension": TEXT("纤维拉伸"),
            "fiber compression/shear": TEXT("纤维压缩/剪切"),
            "matrix tension": TEXT("基体拉伸"),
            "matrix compression": TEXT("基体压缩"),
            "delamination": TEXT("分层"),
        }
        if mode in mapping:
            return mapping[mode]
        if not mode:
            return TEXT("未检测")
        try:
            return str(mode)
        except Exception:
            return TEXT("未检测")

    def _appendAutoResultJsonToTable(self, resultFile, odbFile=""):
        """Append an already-generated automatic result JSON to the GUI table.

        This method performs no ODB access.  It is used after autoSolve has
        already extracted all ODB data and written the final JSON/CSV/TXT
        report, avoiding a second expensive scan of the restart ODB chain.
        """
        if not resultFile or not os.path.isfile(resultFile):
            return False

        with open(resultFile, "r", encoding="utf-8-sig") as resultHandle:
            result = json.load(resultHandle)

        fallbackJobName = os.path.splitext(
            os.path.basename(odbFile))[0] if odbFile else \
            self.form.jobName.getValue()
        jobName = str(result.get("jobName", fallbackJobName))
        peakForceN = self._resultNumber(result.get("peakForce_N"), 0.0)
        peakDisplacement = self._resultNumber(
            result.get("peakDisplacement_mm"))
        nominalStress = self._resultNumber(
            result.get("maximumNominalStress_MPa"), 0.0)
        finalForceN = self._resultNumber(result.get("finalForce_N"))

        dropPercent = None
        if peakForceN > 1.0e-20 and finalForceN is not None:
            dropPercent = max(
                0.0, (peakForceN - abs(finalForceN)) /
                peakForceN * 100.0)

        firstDamage = result.get("firstDamageEvent") or {}
        firstModeRaw = firstDamage.get("mode")
        firstModeText = self._damageModeText(firstModeRaw)
        firstDamageForceN = self._resultNumber(
            firstDamage.get("force_N"))

        kineticPercent = self._resultNumber(
            result.get("ALLKE_ALLIE_atPeak"))
        artificialPercent = self._resultNumber(
            result.get("ALLAE_ALLIE_atPeak"))
        viscousPercent = self._resultNumber(
            result.get("ALLVD_ALLIE_atPeak"))
        equilibriumPercent = self._resultNumber(
            result.get("forceEquilibriumRelativeErrorAtPeak"))

        kineticPercent = (
            None if kineticPercent is None else 100.0 * kineticPercent)
        artificialPercent = (
            None if artificialPercent is None
            else 100.0 * artificialPercent)
        viscousPercent = (
            None if viscousPercent is None else 100.0 * viscousPercent)
        equilibriumPercent = (
            None if equilibriumPercent is None
            else 100.0 * equilibriumPercent)

        deletedStatus = self._resultNumber(
            result.get("deletedElementsBySTATUS_final"))
        deletedSDV1 = self._resultNumber(
            result.get("deletedElementsBySDV1_final"))
        deletedCandidates = [
            int(value) for value in (deletedStatus, deletedSDV1)
            if value is not None]
        deletedElements = (
            max(deletedCandidates) if deletedCandidates else None)

        validStrength = bool(result.get("validStrength", False))
        validityText = (
            TEXT("有效") if validStrength else TEXT("需检查"))

        currentRow = self.table.getNumRows()
        self.table.insertRows(currentRow, 1)
        values = (
            jobName,
            self._resultText(peakForceN / 1000.0, 3),
            self._resultText(peakDisplacement, 4),
            self._resultText(nominalStress, 3),
            self._resultText(dropPercent, 2),
            firstModeText,
            self._resultText(
                None if firstDamageForceN is None
                else firstDamageForceN / 1000.0, 3),
            self._resultText(kineticPercent, 3),
            self._resultText(artificialPercent, 3),
            self._resultText(viscousPercent, 3),
            self._resultText(equilibriumPercent, 3),
            "--" if deletedElements is None else str(deletedElements),
            validityText,
        )
        for columnIndex, value in enumerate(values, start=1):
            self.table.setItemValue(currentRow, columnIndex, value)

        resultDirectory = os.path.dirname(os.path.abspath(resultFile))
        record = {
            "JobName": jobName,
            "PeakForce_kN": peakForceN / 1000.0,
            "PeakDisplacement_mm": peakDisplacement,
            "ResidualStrength_MPa": nominalStress,
            "PeakToFinalDrop_percent": dropPercent,
            "FirstDamageMode": firstModeRaw or "",
            "FirstDamageForce_kN": (
                None if firstDamageForceN is None
                else firstDamageForceN / 1000.0),
            "ALLKE_ALLIE_atPeak_percent": kineticPercent,
            "ALLAE_ALLIE_atPeak_percent": artificialPercent,
            "ALLVD_ALLIE_atPeak_percent": viscousPercent,
            "ForceEquilibriumError_percent": equilibriumPercent,
            "DeletedElements": deletedElements,
            "ValidStrength": validStrength,
            "ResultJSON": os.path.abspath(resultFile),
            "ODB": os.path.abspath(odbFile) if odbFile else "",
        }
        self.resultRecords.append(record)
        self.lastResultDirectory = resultDirectory
        return True

    def omCmdParseODB(self, sender, sel, ptr):
        self.form.cmdType.setValue("parseODB")
        odbFile = self.form.mOdbFileKw.getValue()
        if not odbFile or not os.path.isfile(odbFile):
            raise ValueError(TEXT("请选择存在的 ODB 文件"))

        self.form.issueCommands()

        basename = os.path.basename(odbFile)
        jobNameWithoutExt = os.path.splitext(basename)[0]
        resultFile = os.path.join(
            os.path.dirname(os.path.abspath(odbFile)),
            jobNameWithoutExt + "_Result.json")
        if not os.path.isfile(resultFile):
            raise ValueError(TEXT("后处理结果文件没有生成，请检查消息区错误"))

        with open(resultFile, "r", encoding="utf-8-sig") as resultHandle:
            result = json.load(resultHandle)

        jobName = str(result.get("jobName", jobNameWithoutExt))
        peakForceN = self._resultNumber(result.get("peakForce_N"), 0.0)
        peakDisplacement = self._resultNumber(
            result.get("peakDisplacement_mm"))
        nominalStress = self._resultNumber(
            result.get("maximumNominalStress_MPa"), 0.0)
        finalForceN = self._resultNumber(result.get("finalForce_N"))

        dropPercent = None
        if peakForceN > 1.0e-20 and finalForceN is not None:
            dropPercent = max(
                0.0, (peakForceN - abs(finalForceN)) /
                peakForceN * 100.0)

        firstDamage = result.get("firstDamageEvent") or {}
        firstModeRaw = firstDamage.get("mode")
        firstModeText = self._damageModeText(firstModeRaw)
        firstDamageForceN = self._resultNumber(
            firstDamage.get("force_N"))

        kineticPercent = self._resultNumber(
            result.get("ALLKE_ALLIE_atPeak"))
        artificialPercent = self._resultNumber(
            result.get("ALLAE_ALLIE_atPeak"))
        viscousPercent = self._resultNumber(
            result.get("ALLVD_ALLIE_atPeak"))
        equilibriumPercent = self._resultNumber(
            result.get("forceEquilibriumRelativeErrorAtPeak"))
        # Convert dimensionless ratios to percentages for display.
        kineticPercent = (
            None if kineticPercent is None else 100.0 * kineticPercent)
        artificialPercent = (
            None if artificialPercent is None
            else 100.0 * artificialPercent)
        viscousPercent = (
            None if viscousPercent is None else 100.0 * viscousPercent)
        equilibriumPercent = (
            None if equilibriumPercent is None
            else 100.0 * equilibriumPercent)

        deletedStatus = self._resultNumber(
            result.get("deletedElementsBySTATUS_final"))
        deletedSDV1 = self._resultNumber(
            result.get("deletedElementsBySDV1_final"))
        deletedCandidates = [
            int(value) for value in (deletedStatus, deletedSDV1)
            if value is not None]
        deletedElements = (
            max(deletedCandidates) if deletedCandidates else None)

        validStrength = bool(result.get("validStrength", False))
        validityText = (
            TEXT("有效") if validStrength else TEXT("需检查"))

        currentRow = self.table.getNumRows()
        self.table.insertRows(currentRow, 1)
        values = (
            jobName,
            self._resultText(peakForceN / 1000.0, 3),
            self._resultText(peakDisplacement, 4),
            self._resultText(nominalStress, 3),
            self._resultText(dropPercent, 2),
            firstModeText,
            self._resultText(
                None if firstDamageForceN is None
                else firstDamageForceN / 1000.0, 3),
            self._resultText(kineticPercent, 3),
            self._resultText(artificialPercent, 3),
            self._resultText(viscousPercent, 3),
            self._resultText(equilibriumPercent, 3),
            "--" if deletedElements is None else str(deletedElements),
            validityText,
        )
        for columnIndex, value in enumerate(values, start=1):
            self.table.setItemValue(currentRow, columnIndex, value)

        record = {
            "JobName": jobName,
            "PeakForce_kN": peakForceN / 1000.0,
            "PeakDisplacement_mm": peakDisplacement,
            "ResidualStrength_MPa": nominalStress,
            "PeakToFinalDrop_percent": dropPercent,
            "FirstDamageMode": firstModeRaw or "",
            "FirstDamageForce_kN": (
                None if firstDamageForceN is None
                else firstDamageForceN / 1000.0),
            "ALLKE_ALLIE_atPeak_percent": kineticPercent,
            "ALLAE_ALLIE_atPeak_percent": artificialPercent,
            "ALLVD_ALLIE_atPeak_percent": viscousPercent,
            "ForceEquilibriumError_percent": equilibriumPercent,
            "DeletedElements": deletedElements,
            "ValidStrength": validStrength,
            "ResultJSON": resultFile,
            "ODB": os.path.abspath(odbFile),
        }
        self.resultRecords.append(record)
        self.lastResultDirectory = os.path.dirname(
            os.path.abspath(odbFile))

        if validStrength:
            message = (
                TEXT("剩余强度结果有效：%.3f MPa；峰值载荷：%.3f kN；"
                     "峰值位移：%.4f mm；首损伤：")
                % (nominalStress, peakForceN / 1000.0,
                   peakDisplacement))
            self.form.showMessage(message + firstModeText)
        else:
            warnings = result.get("warnings", [])
            warningText = "; ".join([str(item) for item in warnings])
            self.form.showMessage(
                TEXT("结果尚未通过有效性检查：") +
                TEXT(warningText))
        return

    def omCmdOpenResultFolder(self, sender, sel, ptr):
        resultDirectory = self.lastResultDirectory
        if not resultDirectory:
            odbFile = self.form.mOdbFileKw.getValue()
            if odbFile:
                resultDirectory = os.path.dirname(
                    os.path.abspath(odbFile))
        if not resultDirectory or not os.path.isdir(resultDirectory):
            raise ValueError(TEXT("尚无可打开的结果文件夹"))
        os.startfile(resultDirectory)
        return

    def omCmdExportResultSummary(self, sender, sel, ptr):
        if not self.resultRecords:
            raise ValueError(TEXT("当前没有可导出的结果"))

        outputDirectory = self.lastResultDirectory
        if not outputDirectory:
            outputDirectory = os.getcwd()
        outputPath = os.path.join(
            outputDirectory, "CompositeRepair_Result_Summary.csv")

        headers = (
            "JobName",
            "PeakForce_kN",
            "PeakDisplacement_mm",
            "ResidualStrength_MPa",
            "PeakToFinalDrop_percent",
            "FirstDamageMode",
            "FirstDamageForce_kN",
            "ALLKE_ALLIE_atPeak_percent",
            "ALLAE_ALLIE_atPeak_percent",
            "ALLVD_ALLIE_atPeak_percent",
            "ForceEquilibriumError_percent",
            "DeletedElements",
            "ValidStrength",
            "ResultJSON",
            "ODB",
        )
        with open(outputPath, "w", encoding="utf-8-sig", newline="") as outputFile:
            writer = csv.writer(outputFile)
            writer.writerow(headers)
            for record in self.resultRecords:
                writer.writerow([
                    record.get(header, "") for header in headers])

        self.form.showMessage(
            TEXT("结果汇总已导出：") +
            TEXT(outputPath))
        return


    def _updateBuildButtons(self):
        if self.selectedModifyType == 2:
            self.createModelButton.setText(TEXT("创建连续斜接几何/分区"))
            self.meshModelButton.show()
        else:
            self.createModelButton.setText(TEXT("创建完整有限元模型"))
            self.meshModelButton.hide()
        self.createModelButton.getParent().recalc()
        return

    def _selectModifyType(self, selectedType):
        self.selectedModifyType = selectedType
        self.form.modifyType.setValue(selectedType)
        self.modifyPatchButton.setCheck(selectedType == 0)
        self.modifyStairButton.setCheck(selectedType == 1)
        self.modifyScarfButton.setCheck(selectedType == 2)
        self.parameterPages.setCurrent(selectedType)
        self.parameterPages.recalc()
        self._updateBuildButtons()
        return 1

    def onSelectPatch(self, sender, sel, ptr):
        return self._selectModifyType(0)

    def onSelectStair(self, sender, sel, ptr):
        return self._selectModifyType(1)

    def onSelectScarf(self, sender, sel, ptr):
        return self._selectModifyType(2)

    def processUpdates(self):
        # self.getMatParams()
        current = self.selectedModifyType
        self.form.modifyType.setValue(current)
        self.parameterPages.setCurrent(current)
        self.parameterPages.recalc()
            
        ##############
        type = self.tb_type_sw.getCurrent()
        self.form.tbType.setValue(type)
        shape = self.tb_shape_sw.getCurrent()
        self.form.tbShape.setValue(shape)
        if(shape == 0):
            self.tbHeight.hide()
            self.tbWidth.setLabelText(TEXT("补片直径(mm):"))
            pass
        elif(shape == 1):
            self.tbWidth.setLabelText(TEXT("宽度(mm):"))
            self.tbHeight.show()
        
        ##考虑压缩边界
        f = self.compressBc.getCheck()
        i = 0
        if(f):i=1
        self.form.pressBC.setValue(i)
        
        # 后处理类型
        if self.sw2.getCurrent() == 0:
            self.parseOdbType.setValue(0)
        elif self.sw2.getCurrent() == 1:
            self.parseOdbType.setValue(1)
            
            
    ##加载材料
    def omCmdSelectLoadMaterial(self, sender, sel, ptr):
        return
    


    ##创建模型
    def omCmdSelectCreateModel(self, sender, sel, ptr):
        self.getMatParams()
        self.form.modifyType.setValue(self.selectedModifyType)
        if self.selectedModifyType == 2:
            self.form.cmdType.setValue("createGeometry")
            self.form.showMessage(
                TEXT("正在创建连续斜接几何、铺层分区和胶层几何；"
                     "本步骤不划分网格。"))
        else:
            self.form.cmdType.setValue("createModel")
            self.form.showMessage(TEXT("正在创建完整有限元模型。"))
        self.form.issueCommands()
        return

    def omCmdMeshModel(self, sender, sel, ptr):
        if self.selectedModifyType != 2:
            raise ValueError(
                TEXT("分步划分网格当前仅用于真正连续斜接式"))
        self.getMatParams()
        self.form.modifyType.setValue(2)
        self.form.cmdType.setValue("meshModel")
        self.form.showMessage(
            TEXT("正在对当前连续斜接几何划分网格，并建立装配、Tie、"
                 "边界条件和分析步。"))
        self.form.issueCommands()
        return
    
    ###设置材料
    
    
    
    ##计算求解
    def omCmdSelectSubmit(self, sender, sel, ptr):
        automatic = int(self.form.autoSolve.getValue()) == 1
        self.form.cmdType.setValue(
            "autoSolve" if automatic else "submitJob")
        self.submitButton.disable()
        if automatic:
            self.form.showMessage(
                TEXT("自动求剩余强度已启动：程序会完成初始计算，未破坏时自动Restart续算，并生成结果报告。Abaqus界面在此期间可能暂时无响应。"))
        try:
            self.form.issueCommands()
        except:
            self.submitButton.enable()
            self.submitButton.setText(
                TEXT("提交计算 / 自动求剩余强度"))
            raise
        if automatic:
            self.submitButton.enable()
            self.submitButton.setText(TEXT("自动计算完成"))
            resultFile = os.path.join(
                thisDir, "jobs",
                self.form.jobName.getValue() +
                "_AutoResidualStrength_Result.json")
            if os.path.isfile(resultFile):
                with open(resultFile, "r", encoding="utf-8-sig") as resultHandle:
                    result = json.load(resultHandle)
                strength = self._resultNumber(
                    result.get("maximumNominalStress_MPa"))
                peakForce = self._resultNumber(
                    result.get("peakForce_N"))
                valid = bool(result.get("validStrength", False))

                # The automatic solver has already scanned the initial/restart
                # ODB chain and written Result.json.  Populate the visible
                # result row directly from that JSON instead of reopening ODBs.
                rootOdbFile = os.path.join(
                    thisDir, "jobs",
                    self.form.jobName.getValue() + ".odb")
                tableUpdated = self._appendAutoResultJsonToTable(
                    resultFile, rootOdbFile)

                if strength is not None and peakForce is not None:
                    message = (
                        (TEXT("自动计算完成：剩余强度 %.3f MPa，峰值载荷 %.3f kN，结果状态：")
                         % (strength, peakForce / 1000.0)) +
                        (TEXT("有效") if valid else TEXT("需检查")))
                    if tableUpdated:
                        message += TEXT("；结果已自动写入结果表，无需再次读取ODB")
                    self.form.showMessage(message)
        else:
            self.submitButton.setText(TEXT("已提交，请勿重复点击"))
        return
    
    ###施加边界条件method A
    def omCmdSelectApplyBC(self, sender, sel, ptr):
        self.form.cmdType.setValue("applyBC")
        self.form.issueCommands() 
        return
    
    ##时间边界条件 method B
    def omCmdSelectApplyBCBtDis(self, sender, sel, ptr):
        self.form.cmdType.setValue("applyBCBtDis")
        self.form.issueCommands() 
        return
    
    ###后处理
    def omCmdSelectPostProcess(self, sender, sel, ptr):
        self.form.cmdType.setValue("postProcess")
        self.form.issueCommands() 
        return
    
    
    

    
    


    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    def show(self):
        
        # Note: This method is only necessary because the prototype
        # application allows changes to be made in the dialog code and
        # reloaded while the application is still running. Normally you
        # would not need to have a show() method in your dialog.
        
        # Resize the dialog to its default dimensions to account for
        # any widget changes that may have been made.
        #
        self.resize(max(920, self.getDefaultWidth()),
                    max(680, self.getDefaultHeight()))
        AFXDataDialog.show(self)


####################


###########################################################################
# Class definition
###########################################################################

class Composite_Repair_Strength_AnalysisDBFileHandler(FXObject):

    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    def __init__(self, form, keyword, patterns='*'):
        self.form = form
        self.patterns = patterns
        self.patternTgt = AFXIntTarget(0)
        self.fileNameKw = getattr(form, '%sKw' % keyword)
        self.readOnlyKw = AFXBoolKeyword(None, 'readOnly', AFXBoolKeyword.TRUE_FALSE)
        FXObject.__init__(self)
        FXMAPFUNC(self, SEL_COMMAND, AFXMode.ID_ACTIVATE, Composite_Repair_Strength_AnalysisDBFileHandler.activate)

    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    def activate(self, sender, sel, ptr):
       fileDb = AFXFileSelectorDialog(getAFXApp().getAFXMainWindow(), 'Select a File',
           self.fileNameKw, self.readOnlyKw,
           AFXSELECTFILE_ANY, self.patterns, self.patternTgt)
       fileDb.setReadOnlyPatterns('*.odb')
       fileDb.create()
       fileDb.showModal()

############文件选择

class FileDBFileHandler(FXObject):

    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    def __init__(self, form, keyword, patterns='*',title="Select a File"):
        self.titleKw = title

        self.form = form
        self.patterns = patterns
        self.patternTgt = AFXIntTarget(0)
        self.fileNameKw = getattr(form, '%sKw' % keyword)
        self.readOnlyKw = AFXBoolKeyword(None, 'readOnly', AFXBoolKeyword.TRUE_FALSE)
        FXObject.__init__(self)
        FXMAPFUNC(self, SEL_COMMAND, AFXMode.ID_ACTIVATE, FileDBFileHandler.activate)

    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    def activate(self, sender, sel, ptr):
        
        fileDb = AFXFileSelectorDialog(getAFXApp().getAFXMainWindow(), self.titleKw,
           self.fileNameKw, self.readOnlyKw,
           AFXSELECTFILE_ANY, self.patterns, self.patternTgt)
        if '.odb' in self.patterns.lower():
            fileDb.setReadOnlyPatterns('*.odb')
        fileDb.create()
        fileDb.showModal()

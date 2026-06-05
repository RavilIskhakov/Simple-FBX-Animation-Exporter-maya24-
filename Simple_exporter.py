"""
Simple FBX Animation Exporter — Maya 2026
==========================================
Чистый экспортёр выделения в FBX с анимацией. Без льва, групп, рефов.

Что делает:
  - Берёт текущее выделение в Outliner.
  - Запекает кости среди выделения в ключи на каждом кадре (если включено).
  - Экспортирует в FBX с анимацией.

Запуск: скопируй ВЕСЬ код в Script Editor (Python) и выполни.
"""

import os
import maya.cmds as cmds
import maya.mel as mel
import maya.OpenMayaUI as omui

try:
    from PySide6 import QtWidgets, QtCore
    from shiboken6 import wrapInstance
except ImportError:
    from PySide2 import QtWidgets, QtCore
    from shiboken2 import wrapInstance


def _maya_main_window():
    ptr = omui.MQtUtil.mainWindow()
    return wrapInstance(int(ptr), QtWidgets.QWidget) if ptr else None


def bake_selection(start, end):
    """Запекает кости среди выделения в ключи на каждом кадре."""
    sel = cmds.ls(selection=True, long=True)
    joints = cmds.ls(sel, type="joint", long=True) or []
    joints += cmds.listRelatives(sel, allDescendents=True, type="joint",
                                 fullPath=True) or []
    joints = list(set(joints))
    if not joints:
        print("[bake] костей не найдено — пропускаю.")
        return
    print("[bake] запекаю %d костей, %d-%d..." % (len(joints), start, end))
    cmds.bakeResults(
        joints, simulation=True, time=(start, end), sampleBy=1,
        disableImplicitControl=True, preserveOutsideKeys=False,
        minimizeRotation=True, shape=True,
        attribute=["tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz"],
    )
    print("[bake] готово.")


def export_fbx(file_path, do_bake, start, end):
    """Экспортирует выделение в FBX с анимацией и скином."""
    if not cmds.pluginInfo("fbxmaya", query=True, loaded=True):
        cmds.loadPlugin("fbxmaya")

    if not file_path.lower().endswith(".fbx"):
        file_path += ".fbx"
    out_dir = os.path.dirname(file_path)
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    # расширяем выделение на ВСЮ иерархию вниз — иначе FBX не возьмёт
    # вложенные меши и кости, и скин не уйдёт
    sel = cmds.ls(selection=True, long=True)
    descendants = cmds.listRelatives(sel, allDescendents=True, fullPath=True) or []
    full = list(dict.fromkeys(sel + descendants))
    cmds.select(full, replace=True)

    n_meshes = len(cmds.ls(full, type="mesh", long=True) or [])
    n_joints = len(cmds.ls(full, type="joint", long=True) or [])
    print("[fbx] в экспорт идёт %d узлов (mesh: %d, joint: %d)"
          % (len(full), n_meshes, n_joints))

    mel.eval('FBXResetExport;')
    mel.eval('FBXExportFileVersion -v FBX202000;')
    # смус-группы и сглаживание
    mel.eval('FBXExportSmoothingGroups -v true;')   # смус-группы как в Maya
    mel.eval('FBXExportSmoothMesh -v true;')        # writes subdivided smooth mesh
    mel.eval('FBXExportHardEdges -v false;')        # не схлопывать hard edges в дубли вершин
    mel.eval('FBXExportTriangulate -v false;')      # не триангулировать (UE сам сделает корректно)
    mel.eval('FBXExportTangents -v true;')          # тангенты для нормал-мапов
    mel.eval('FBXExportSkins -v true;')
    mel.eval('FBXExportSkeletonDefinitions -v true;')
    mel.eval('FBXExportShapes -v true;')
    mel.eval('FBXExportInputConnections -v false;')
    mel.eval('FBXExportBakeComplexAnimation -v %s;' % ("true" if do_bake else "false"))
    mel.eval('FBXExportBakeComplexStart -v %d;' % int(start))
    mel.eval('FBXExportBakeComplexEnd -v %d;' % int(end))
    mel.eval('FBXExportBakeComplexStep -v 1;')
    mel.eval('FBXExportBakeResampleAnimation -v true;')
    mel.eval('FBXExportCameras -v false;')
    mel.eval('FBXExportLights -v false;')
    mel.eval('FBXExportConstraints -v false;')
    mel.eval('FBXExportUpAxis y;')

    fbx_path = file_path.replace("\\", "/")
    mel.eval('FBXExport -f "%s" -s;' % fbx_path)
    print("[fbx] экспортировано: %s" % fbx_path)
    return file_path


class SimpleFbxExporter(QtWidgets.QDialog):

    def __init__(self, parent=None):
        super(SimpleFbxExporter, self).__init__(parent or _maya_main_window())
        self.setObjectName("simpleFbxExporterWindow")
        self.setWindowTitle("Simple FBX Exporter")
        self.setMinimumWidth(420)

        main = QtWidgets.QVBoxLayout(self)
        main.setContentsMargins(12, 12, 12, 12)
        main.setSpacing(8)

        main.addWidget(QtWidgets.QLabel(
            "Выдели нужное в Outliner и жми Export."))

        self.cb_bake = QtWidgets.QCheckBox("Запекать кости в ключи")
        self.cb_bake.setChecked(True)
        main.addWidget(self.cb_bake)

        # диапазон
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Start:"))
        self.sb_start = QtWidgets.QSpinBox()
        self.sb_start.setRange(-100000, 100000)
        row.addWidget(self.sb_start)
        row.addSpacing(12)
        row.addWidget(QtWidgets.QLabel("End:"))
        self.sb_end = QtWidgets.QSpinBox()
        self.sb_end.setRange(-100000, 100000)
        row.addWidget(self.sb_end)
        row.addStretch()
        btn_tl = QtWidgets.QPushButton("Из таймлайна")
        btn_tl.clicked.connect(self._load_range)
        row.addWidget(btn_tl)
        main.addLayout(row)

        # путь
        path_row = QtWidgets.QHBoxLayout()
        self.le_path = QtWidgets.QLineEdit()
        self.le_path.setPlaceholderText("путь/к/файлу.fbx")
        path_row.addWidget(self.le_path)
        btn_browse = QtWidgets.QPushButton("Обзор…")
        btn_browse.clicked.connect(self._browse)
        path_row.addWidget(btn_browse)
        main.addLayout(path_row)

        # экспорт
        self.btn_export = QtWidgets.QPushButton("Export FBX")
        self.btn_export.setMinimumHeight(34)
        self.btn_export.clicked.connect(self._on_export)
        main.addWidget(self.btn_export)

        self.lbl_status = QtWidgets.QLabel("")
        self.lbl_status.setWordWrap(True)
        main.addWidget(self.lbl_status)

        self._load_range()

    def _load_range(self):
        self.sb_start.setValue(int(cmds.playbackOptions(query=True, minTime=True)))
        self.sb_end.setValue(int(cmds.playbackOptions(query=True, maxTime=True)))

    def _browse(self):
        start_dir = self.le_path.text() or cmds.workspace(query=True, rootDirectory=True)
        result = cmds.fileDialog2(
            fileMode=0, caption="Сохранить FBX",
            startingDirectory=start_dir,
            fileFilter="FBX Files (*.fbx)", dialogStyle=2)
        if result:
            self.le_path.setText(result[0])

    def _status(self, text, ok=True):
        self.lbl_status.setStyleSheet("color: %s;" % ("#7CFC7C" if ok else "#FF7C7C"))
        self.lbl_status.setText(text)

    def _on_export(self):
        path = self.le_path.text().strip()
        if not path:
            self._status("Укажи путь к файлу.", ok=False)
            return
        if not cmds.ls(selection=True):
            self._status("Ничего не выделено.", ok=False)
            return
        start = self.sb_start.value()
        end = self.sb_end.value()
        if end < start:
            self._status("End меньше Start.", ok=False)
            return
        do_bake = self.cb_bake.isChecked()

        cmds.undoInfo(openChunk=True)
        try:
            if do_bake:
                bake_selection(start, end)
            result = export_fbx(path, do_bake, start, end)
            self._status("Готово: %s" % result, ok=True)
        except Exception as exc:
            self._status("Ошибка: %s" % exc, ok=False)
            raise
        finally:
            cmds.undoInfo(closeChunk=True)


_ui = None


def show():
    global _ui
    if _ui is not None:
        try:
            _ui.close()
            _ui.deleteLater()
        except Exception:
            pass
        _ui = None
    _ui = SimpleFbxExporter()
    _ui.show()


# автозапуск при вставке в Script Editor
show()
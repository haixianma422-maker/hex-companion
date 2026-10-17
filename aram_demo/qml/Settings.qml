import QtQuick
import QtQuick.Effects
import QtQuick.Dialogs

// The 480×684 settings dialog (T05–T09 of the V2 handoff). Three tabs over one form;
// nothing is applied until 保存并应用. Only the page body scrolls on a short desktop.
Window {
    id: dialog
    readonly property var form: settings.form
    readonly property int pageHeight: height - 196
    property var fields: ({})
    title: "海克斯随行 · 设置"
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
    color: "transparent"
    width: 480
    height: Math.min(684, Screen.desktopAvailableHeight)
    x: Screen.virtualX + (Screen.desktopAvailableWidth - width) / 2
    y: Screen.virtualY + (Screen.desktopAvailableHeight - height) / 2
    visible: true

    function register(id, item) { fields[id] = item }
    Connections {
        target: settings
        function onFocusRequested(id) {
            const item = dialog.fields[id] || dialog.fields[id.split(".").slice(0, 2).join(".")]
            if (!item) return
            const page = [common, shortcuts, advanced][dialog.form.tab]
            const top = item.mapToItem(page.contentItem, 0, 0).y
            if (top < page.contentY) page.contentY = Math.max(0, top - 4)
            else if (top + item.height > page.contentY + page.height)
                page.contentY = Math.min(page.contentHeight - page.height, top + item.height - page.height + 4)
            item.takeFocus()
        }
    }

    Shortcut { sequence: "Esc"; onActivated: settings.dismiss() }

    Rectangle {
        id: frame
        anchors.fill: parent
        radius: 16
        color: Theme.bg
        border.color: Theme.line

        // ---- title bar ----
        Brand { x: 20; y: 15; width: 24; height: 24 }
        Text {
            x: 56; y: 12; height: 28; verticalAlignment: Text.AlignVCenter; text: "随行设置"
            font.family: Theme.font; font.pixelSize: 18; font.bold: true; color: Theme.text
        }
        Item {
            width: 420; height: 52
            DragHandler { target: null; onActiveChanged: if (active) dialog.startSystemMove() }
        }
        PanelButton {
            x: 435; y: 10; width: 28; height: 28; radius: 8; icon: "close"
            onClicked: settings.dismiss()
        }

        // ---- tabs ----
        Rectangle {
            id: tabs
            y: 52; width: 480; height: 56; radius: 12; color: Theme.lilac
            Rectangle {
                y: 9; width: 142; height: 38; radius: 19; color: Theme.bg
                x: 22 + dialog.form.tab * 147
                Behavior on x { XAnimator { duration: Theme.ms(220); easing.type: Easing.OutBack; easing.overshoot: 1.2 } }
            }
            Repeater {
                model: ["常用设置", "快捷键", "识别与连接"]
                Item {
                    x: 22 + index * 147; y: 9; width: 142; height: 38
                    Text {
                        anchors.centerIn: parent; text: modelData
                        font.family: Theme.font; font.pixelSize: 16; font.bold: true
                        color: index === dialog.form.tab ? Theme.text : Theme.ink
                        Behavior on color { ColorAnimation { duration: Theme.ms(Theme.fast) } }
                    }
                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: settings.selectTab(index) }
                }
            }
        }

        // ---- pages ----
        Item {
            id: pages
            x: 20; y: 124; width: 440; height: dialog.pageHeight

            Page {
                id: common
                index: 0
                Text { x: 4; y: 5; height: 26; text: "数据来源"; font.family: Theme.font; font.pixelSize: 18; font.bold: true; color: Theme.text }
                SourceSwitch {
                    x: 188; y: 2; width: 248; height: 38; fontSize: 14
                    labels: ["OP.GG", "101 数据站"]
                    value: dialog.form.source
                    onChosen: source => settings.setValue("source", source)
                }
                Text { x: 188; y: 49; width: 248; text: "101：S–C · OP.GG：S–E"; font.family: Theme.font; font.pixelSize: 13; color: Theme.muted }
                Text {
                    x: 188; y: 68; width: 248; text: "召唤师技能缺失时使用 OP.GG 补充"; wrapMode: Text.Wrap
                    font.family: Theme.font; font.pixelSize: 12; color: Theme.muted
                }
                Divider { y: 104 }
                Text { x: 4; y: 117; text: "自动识别海克斯"; font.family: Theme.font; font.pixelSize: 18; font.bold: true; color: Theme.text }
                Text { x: 4; y: 146; text: "局内选择海克斯时自动识别"; font.family: Theme.font; font.pixelSize: 13; color: Theme.muted }
                Toggle { x: 382; y: 124; checked: dialog.form.auto; onToggled: v => settings.setValue("auto", v) }
                Divider { y: 178 }
                Text { x: 4; y: 191; text: "动效"; font.family: Theme.font; font.pixelSize: 18; font.bold: true; color: Theme.text }
                Text { x: 4; y: 220; text: "展开、切换与结果更新"; font.family: Theme.font; font.pixelSize: 13; color: Theme.muted }
                Toggle { x: 382; y: 198; checked: dialog.form.animations; onToggled: v => settings.setValue("animations", v) }
                Divider { y: 252 }
                Text { x: 4; y: 266; text: "手动修正"; font.family: Theme.font; font.pixelSize: 18; font.bold: true; color: Theme.text }
                Text {
                    x: 278; y: 270; width: 158; text: "仅当前英雄生效"; horizontalAlignment: Text.AlignRight
                    font.family: Theme.font; font.pixelSize: 11; color: Theme.muted
                }
                Repeater {
                    model: 3
                    Item {
                        y: 304 + index * 54; width: 440; height: 44
                        Text {
                            x: 4; width: 54; height: 44; verticalAlignment: Text.AlignVCenter
                            text: ["左侧", "中间", "右侧"][index]
                            font.family: Theme.font; font.pixelSize: 14; color: Theme.text
                        }
                        ChoiceField {
                            x: 74
                            popupLayer: frame
                            value: dialog.form.choices[index]
                            icon: dialog.form.choiceIcons[index]
                            options: dialog.form.options
                            optionIcons: dialog.form.optionIcons
                            onChosen: v => settings.setValue("choice." + index, v)
                            Component.onCompleted: dialog.register("choice." + index, this)
                        }
                    }
                }
                Text { x: 4; y: 466; text: dialog.form.scanKey + " 恢复自动识别"; font.family: Theme.font; font.pixelSize: 12; color: Theme.muted }
            }

            Page {
                id: shortcuts
                index: 1
                Text { x: 4; y: 6; text: "全局快捷键"; font.family: Theme.font; font.pixelSize: 18; font.bold: true; color: Theme.text }
                Text { x: 4; y: 42; text: "点击输入框后按下组合键"; font.family: Theme.font; font.pixelSize: 13; color: Theme.muted }
                Repeater {
                    model: [["scan", "重新识别"], ["refresh", "刷新资料"], ["toggle", "展开 / 收起"]]
                    Item {
                        y: 86 + index * 62; width: 440; height: 46
                        Text {
                            x: 4; width: 158; height: 46; verticalAlignment: Text.AlignVCenter; text: modelData[1]
                            font.family: Theme.font; font.pixelSize: 17; font.bold: true; color: Theme.text
                        }
                        Field {
                            x: 172; width: 264; height: 46; fontSize: 18; inset: 14; capture: true
                            text: dialog.form.hotkeys[index]
                            error: dialog.form.fieldErrors["hotkey." + modelData[0]] || ""
                            onEdited: v => settings.setValue("hotkey." + modelData[0], v)
                            Component.onCompleted: dialog.register("hotkey." + modelData[0], this)
                        }
                    }
                }
                Divider { y: 292 }
                Icon { x: 4; y: 324; name: "info"; color: Theme.muted }
                Text { x: 36; y: 321; text: "Esc 将面板收起为浮标"; font.family: Theme.font; font.pixelSize: 13; color: Theme.muted }
                Icon { x: 4; y: 364; name: "info"; color: Theme.muted }
                Text { x: 36; y: 361; width: 400; text: "设置窗口打开时暂停全局快捷键"; wrapMode: Text.Wrap; font.family: Theme.font; font.pixelSize: 13; color: Theme.muted }
                LinkText { x: 4; y: 426; text: "恢复默认快捷键"; onClicked: settings.resetHotkeys() }
            }

            Page {
                id: advanced
                index: 2
                readonly property color tone: dialog.form.connectionTone === "error" ? Theme.error
                                            : dialog.form.connectionTone === "accent" ? Theme.accent : Theme.muted
                Text { x: 4; y: 6; text: "标题识别区域"; font.family: Theme.font; font.pixelSize: 18; font.bold: true; color: Theme.text }
                Text {
                    x: 190; y: 10; width: 246; text: "相对游戏窗口，坐标范围 0–1"; horizontalAlignment: Text.AlignRight
                    font.family: Theme.font; font.pixelSize: 11; color: Theme.muted
                }
                Rectangle {
                    x: 4; y: 48; width: 432; height: 146; radius: 10; color: "#14121C"
                    Repeater {
                        model: 3
                        Rectangle {
                            x: 8 + index * 140; y: 8; width: 128; height: 128; radius: 6; color: "#252337"
                            Text {
                                x: 48; y: 2; width: 32; text: ["左", "中", "右"][index]; horizontalAlignment: Text.AlignHCenter
                                font.family: Theme.font; font.pixelSize: 13; color: Theme.muted
                            }
                            Rectangle { x: 6; y: 24; width: 116; height: 98; radius: 5; color: "#1C1A2B" }
                            Rectangle {
                                // The title region: a dashed frame in the Tk sketch.
                                x: 13; y: 31; width: 102; height: 20; color: "transparent"
                                border.color: Theme.lilac; border.width: 1.5; radius: 2; opacity: .8
                            }
                            Item {
                                x: 41; y: 61; width: 46; height: 46
                                Icon { anchors.fill: parent; visible: !art.ready; name: "question"; color: Theme.muted }
                                RoundImage { id: art; anchors.fill: parent; source: dialog.form.regionIcons[index]; radius: 0; fillMode: Image.PreserveAspectFit }
                            }
                        }
                    }
                }
                Text {
                    x: 4; y: 179; width: 432; text: "区域示意 · 非实时画面"; horizontalAlignment: Text.AlignRight
                    font.family: Theme.font; font.pixelSize: 10; color: Theme.muted
                }
                Repeater {
                    model: ["x1", "y1", "x2", "y2"]
                    Text {
                        x: 64 + index * 96; y: 214; width: 84; text: modelData; horizontalAlignment: Text.AlignHCenter
                        font.family: Theme.font; font.pixelSize: 12; color: Theme.muted
                    }
                }
                Repeater {
                    model: 3
                    Item {
                        id: row
                        property int rowIndex: index
                        y: 238 + index * 38; width: 440; height: 32
                        Text {
                            x: 4; width: 52; height: 32; verticalAlignment: Text.AlignVCenter
                            text: ["左侧", "中间", "右侧"][index]
                            font.family: Theme.font; font.pixelSize: 14; color: Theme.text
                        }
                        Repeater {
                            model: 4
                            Field {
                                x: 64 + index * 96; width: 84; height: 32; radius: 8; fontSize: 13; center: true
                                text: dialog.form.regions[row.rowIndex][index]
                                error: dialog.form.fieldErrors["region." + row.rowIndex] || ""
                                onEdited: v => settings.setValue("region." + row.rowIndex + "." + index, v)
                                Component.onCompleted: dialog.register("region." + row.rowIndex + "." + index, this)
                            }
                        }
                    }
                }
                LinkText { x: 4; y: 356; text: "恢复 16:9 预设"; fontSize: 12; onClicked: settings.resetRegions() }
                Divider { y: 390 }
                Text { x: 4; y: 406; text: "客户端连接"; font.family: Theme.font; font.pixelSize: 18; font.bold: true; color: Theme.text }
                Rectangle { x: 148; y: 414; width: 8; height: 8; radius: 4; color: advanced.tone }
                Text {
                    x: 164; y: 408; width: 272; height: 22; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight
                    text: dialog.form.connection
                    font.family: Theme.font; font.pixelSize: 13; color: advanced.tone
                }
                Field {
                    x: 4; y: 444; width: 296; height: 38; fontSize: 13; fill: Theme.raised
                    text: dialog.form.path
                    error: dialog.form.fieldErrors["path"] || ""
                    onEdited: v => settings.setValue("path", v)
                    Component.onCompleted: dialog.register("path", this)
                }
                Rectangle {
                    x: 314; y: 444; width: 122; height: 38; radius: 14
                    color: browseHover.hovered ? Theme.raised : "transparent"
                    border.color: "#645A7A"
                    Behavior on color { ColorAnimation { duration: Theme.ms(Theme.fast) } }
                    Text { anchors.centerIn: parent; text: "选择安装目录"; font.family: Theme.font; font.pixelSize: 13; color: Theme.text }
                    HoverHandler { id: browseHover; cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: folders.open() }
                }
            }
        }

        // ---- footer ----
        Rectangle {
            y: dialog.height - 66; width: 480; height: 66; radius: 16; color: Theme.footer
            Rectangle { width: 480; height: 20; color: Theme.footer }
            Rectangle { width: 480; height: 1; color: Theme.line }
            Rectangle {
                x: 24; y: 10; width: 184; height: 44; radius: 22
                color: cancelHover.hovered ? Theme.raised : Theme.footer
                border.color: "#645A7A"
                Behavior on color { ColorAnimation { duration: Theme.ms(Theme.fast) } }
                Text { anchors.centerIn: parent; text: "取消"; font.family: Theme.font; font.pixelSize: 16; font.bold: true; color: Theme.text }
                HoverHandler { id: cancelHover; cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: settings.dismiss() }
            }
            PanelButton {
                x: 224; y: 10; width: 232; height: 44; kind: "primary"; fontSize: 16
                text: dialog.form.applied ? "已应用" : "保存并应用"
                onClicked: settings.apply()
            }
        }
    }

    FolderDialog {
        id: folders
        title: "选择英雄联盟安装目录"
        onAccepted: settings.choosePath(selectedFolder)
    }

    component Divider: Rectangle { x: 4; width: 432; height: 1; color: Theme.line }

    component LinkText: Text {
        signal clicked()
        property int fontSize: 13
        font.family: Theme.font; font.pixelSize: fontSize; font.underline: true
        color: hovered.hovered ? Theme.text : Theme.muted
        HoverHandler { id: hovered; cursorShape: Qt.PointingHandCursor }
        TapHandler { onTapped: parent.clicked() }
    }

    // One tab body: an error banner above 488px of content; only this part scrolls.
    // Inline components do not see this file's ids, so it reads the form directly.
    component Page: Flickable {
        id: page
        property int index
        default property alias content: body.data
        readonly property string error: settings.form.errors[index]
        width: 440; height: parent.height
        visible: settings.form.tab === index
        opacity: 0
        clip: true
        contentWidth: 440; contentHeight: 488 + (error ? 32 : 0)
        boundsBehavior: Flickable.StopAtBounds
        onVisibleChanged: if (visible) { opacity = 0; fadeIn.restart() }
        Component.onCompleted: if (visible) opacity = 1
        OpacityAnimator { id: fadeIn; target: page; to: 1; duration: Theme.ms(160) }
        Rectangle {
            visible: !!page.error
            width: 440; height: 30; radius: 8; color: Theme.surface
            Text {
                x: 10; width: 420; height: 30; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight
                text: page.error; font.family: Theme.font; font.pixelSize: 12; color: Theme.error
            }
        }
        Item { id: body; y: page.error ? 32 : 0; width: 440; height: 488 }
        Rectangle {
            parent: page.parent
            visible: page.visible && page.contentHeight > page.height + 1
            x: 448; y: page.visibleArea.yPosition * page.height
            width: 4; radius: 2; color: Theme.scrollThumb
            height: Math.max(24, page.visibleArea.heightRatio * page.height)
        }
    }
}

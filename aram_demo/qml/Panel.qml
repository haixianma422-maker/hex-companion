import QtQuick
import QtQuick.Effects

// The 360px panel at the V2 handoff's logical coordinates: SELECT is 540 tall, GAME 580.
// The header and footer stay put; on a short work area only the middle scrolls.
Rectangle {
    id: root
    objectName: "panelContent"
    readonly property var view: panel.view
    readonly property bool game: view.game === true
    width: 360
    radius: 14
    color: Theme.bg

    // ---- hero switch: fade-through, never a cross-blend of two names ----
    property var shown: ({ heroId: -1 })
    function adopt() {
        shown = { heroId: view.heroId, heroName: view.heroName, heroTitle: view.heroTitle, heroTier: view.heroTier,
                  heroTip: view.heroTip, splash: view.splash, focusX: view.focusX, focusY: view.focusY }
    }
    Component.onCompleted: adopt()
    Connections {
        target: panel
        function onViewChanged() {
            if (root.view.heroId !== root.shown.heroId && root.shown.heroId > 0 && root.view.heroId > 0) heroSwap.restart()
            else if (!heroSwap.running) root.adopt()
        }
    }
    SequentialAnimation {
        id: heroSwap
        ParallelAnimation {
            OpacityAnimator { target: heroText; to: 0; duration: Theme.ms(110); easing.type: Easing.InCubic }
            XAnimator { target: heroText; to: -8; duration: Theme.ms(110); easing.type: Easing.InCubic }
        }
        ScriptAction { script: root.adopt() }
        PropertyAction { target: heroText; property: "x"; value: 12 }
        ParallelAnimation {
            OpacityAnimator { target: heroText; to: 1; duration: Theme.ms(240); easing.type: Easing.OutCubic }
            XAnimator { target: heroText; to: 0; duration: Theme.ms(280); easing.type: Easing.OutQuint }
        }
    }

    // ---- header ----
    Brand { x: 16; y: 10; width: 20; height: 20 }
    Text {
        x: 45; y: 8; height: 24; verticalAlignment: Text.AlignVCenter
        text: root.view.title || ""
        font.family: Theme.font; font.pixelSize: 17; font.bold: true; color: Theme.text
    }
    Item {
        // Drag strip; a double click advances the developer preview.
        width: 280; height: 38
        DragHandler { target: null; onActiveChanged: if (active) Window.window.startSystemMove() }
        TapHandler { onDoubleTapped: panel.preview() }
    }
    PanelButton {
        x: 287; y: 4; width: 28; height: 28; radius: 8; icon: "minus"
        tip: tip; tipText: "收起为浮标"; onClicked: panel.collapse()
    }
    PanelButton {
        x: 321; y: 4; width: 28; height: 28; radius: 8; icon: "settings"
        tip: tip; tipText: "设置"; onClicked: panel.settings()
    }
    Rectangle { visible: !root.game; x: 12; y: 38; width: 336; height: 1; color: Theme.line }
    Rectangle { x: 16; y: root.game ? 50 : 55; width: 8; height: 8; radius: 4; color: Theme.accent }
    Text {
        x: 32; y: root.game ? 43 : 48; height: 22; verticalAlignment: Text.AlignVCenter
        text: root.view.statusLabel || ""
        font.family: Theme.font; font.pixelSize: 13; font.bold: true; color: Theme.text
    }
    SourceSwitch {
        x: 236; y: root.game ? 42 : 46
        value: root.view.source || "opgg"
        onChosen: source => panel.chooseSource(source)
    }

    // ---- middle ----
    Flickable {
        id: body
        objectName: "panelBody"
        y: root.view.top || 75
        width: 360
        height: root.height - y - (root.view.footer || 58)
        contentHeight: (root.view.baseHeight || 540) - y - (root.view.footer || 58)
        interactive: contentHeight > height + 1
        boundsBehavior: Flickable.StopAtBounds
        clip: true

        Item {
            // Children use the panel's absolute logical coordinates.
            y: -body.y
            width: 360; height: root.view.baseHeight || 540

            // Hero banner. GAME is shorter and carries a lilac band with the skill order.
            Item {
                id: heroBox
                x: root.game ? 4 : 6; y: root.game ? 68 : 75
                width: root.game ? 352 : 348; height: root.game ? 138 : 106
                Rectangle { anchors.fill: parent; radius: 8; color: Theme.lilac }
                Item {
                    id: heroArt
                    width: parent.width; height: root.game ? 84 : parent.height
                    layer.enabled: true
                    layer.effect: MultiEffect { maskEnabled: true; maskSource: heroMask }
                    Splash {
                        anchors.fill: parent
                        focusX: root.shown.focusX || .72; focusY: root.shown.focusY || .42
                        source: root.shown.splash || ""
                    }
                    Rectangle {
                        anchors.fill: parent
                        gradient: Gradient {
                            orientation: Gradient.Horizontal
                            GradientStop { position: 0; color: Theme.lilac }
                            GradientStop { position: .34; color: Theme.lilac }
                            GradientStop { position: .62; color: Qt.rgba(.914, .886, .969, 0) }
                        }
                    }
                    Hint { tip: tip; text: root.shown.heroTip || "" }
                }
                Item {
                    id: heroMask
                    width: heroArt.width; height: heroArt.height; visible: false; layer.enabled: true
                    Rectangle { anchors.fill: parent; radius: 8 }
                    Rectangle { visible: root.game; y: parent.height - 8; width: parent.width; height: 8 }
                }
                Item {
                    id: heroText
                    objectName: "heroText"
                    width: parent.width; height: root.game ? 84 : parent.height
                    Text {
                        id: heroName
                        x: root.game ? 12 : 14; y: root.game ? 9 : 21; height: root.game ? 40 : 44
                        width: root.game ? 150 : 170
                        text: root.shown.heroName || ""
                        fontSizeMode: Text.HorizontalFit; minimumPixelSize: 22
                        verticalAlignment: Text.AlignVCenter
                        font.family: Theme.font; font.pixelSize: root.game ? 30 : 34; font.bold: true; color: Theme.ink
                    }
                    Rectangle {
                        visible: !root.game
                        x: heroName.x + heroName.contentWidth + 8; y: 35; width: 30; height: 22; radius: 11
                        color: Theme.tierPill
                        Text {
                            anchors.centerIn: parent; text: root.shown.heroTier || ""
                            font.family: Theme.font; font.pixelSize: 14; font.bold: true; color: Theme.ink
                        }
                    }
                    Text {
                        x: heroName.x; y: root.game ? 51 : 70; height: 24; width: 180
                        text: root.shown.heroTitle || ""
                        elide: Text.ElideRight
                        font.family: Theme.font; font.pixelSize: root.game ? 14 : 15; font.bold: true; color: Theme.inkMuted
                    }
                }
                // GAME: skill order in the lilac band.
                Item {
                    visible: root.game
                    y: 84; width: parent.width; height: 54
                    opacity: root.view.sourcePending ? .54 : 1
                    Behavior on opacity { OpacityAnimator { duration: Theme.ms(Theme.normal) } }
                    Text {
                        x: 12; y: 18; height: 20; verticalAlignment: Text.AlignVCenter; text: "技能优先级"
                        font.family: Theme.font; font.pixelSize: 13; font.bold: true; color: Theme.ink
                    }
                    Text {
                        x: 94; y: 8; width: 246; height: 40; visible: (root.view.skills || []).length === 0
                        text: root.view.skillText || ""
                        horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                        font.family: Theme.font; font.pixelSize: 14; color: Theme.ink
                    }
                    Repeater {
                        model: root.view.skills || []
                        Rectangle {
                            x: 94 + index * 48; y: 8; width: 40; height: 40; radius: 6
                            color: Theme.tierPill; border.color: "#CBBEE4"
                            Icon { anchors.centerIn: parent; visible: !skillArt.ready; name: "question"; color: Theme.ink; width: 24; height: 24 }
                            RoundImage { id: skillArt; anchors.fill: parent; anchors.margins: 1; source: modelData.icon; radius: 5 }
                            Rectangle {
                                x: 26; y: 24; width: 14; height: 16; radius: 3; color: Theme.bg
                                Text {
                                    anchors.centerIn: parent; text: modelData.key
                                    font.family: Theme.font; font.pixelSize: 11; font.bold: true; color: Theme.text
                                }
                            }
                            Hint { tip: tip; text: modelData.tip }
                        }
                    }
                    Text {
                        x: 194; y: 18; width: 146; height: 20; verticalAlignment: Text.AlignVCenter
                        visible: (root.view.skills || []).length === 2
                        text: root.view.skillText || ""
                        font.family: Theme.font; font.pixelSize: 14; font.bold: true; color: Theme.ink
                    }
                }
            }

            // ---- SELECT ----
            Item {
                visible: !root.game
                width: 360; height: 540
                Item {
                    visible: root.view.stage === "select"
                    y: 191; width: 360; height: 44
                    opacity: root.view.sourcePending ? .54 : 1
                    Behavior on opacity { OpacityAnimator { duration: Theme.ms(Theme.normal) } }
                    Text {
                        x: 16; y: 10; height: 22; verticalAlignment: Text.AlignVCenter; text: "召唤师技能"
                        font.family: Theme.font; font.pixelSize: 14; font.bold: true; color: Theme.text
                    }
                    Text {
                        x: 102; y: 4; width: 151; height: 32; visible: (root.view.spells || []).length !== 2
                        text: root.view.spellText || ""
                        horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                        font.family: Theme.font; font.pixelSize: 12; color: Theme.text
                    }
                    Repeater {
                        model: root.view.spells || []
                        Item {
                            x: 102 + index * 86; y: 4; width: 66; height: 32
                            Rectangle {
                                width: 32; height: 32; radius: 6; color: Theme.surface; border.color: Theme.iconBorder
                                Icon { anchors.centerIn: parent; visible: !spellArt.ready; name: "question"; color: Theme.muted; width: 20; height: 20 }
                                RoundImage { id: spellArt; anchors.fill: parent; anchors.margins: 1; source: modelData.icon; radius: 5 }
                            }
                            Text {
                                x: 37; y: 6; height: 20; verticalAlignment: Text.AlignVCenter
                                text: modelData.name
                                font.family: Theme.font; font.pixelSize: 12; color: Theme.text
                            }
                            Hint { tip: tip; text: modelData.tip }
                        }
                    }
                    Text {
                        x: 170; y: 11; width: 12; height: 20; visible: (root.view.spells || []).length === 2
                        text: "+"; horizontalAlignment: Text.AlignHCenter
                        font.family: Theme.font; font.pixelSize: 12; color: Theme.muted
                    }
                    Text {
                        x: 270; y: 12; width: 74; height: 18
                        text: root.view.spellSupplement || ""; horizontalAlignment: Text.AlignRight
                        font.family: Theme.font; font.pixelSize: 10; color: Theme.muted
                    }
                }
                Rectangle { x: 12; y: 239; width: 336; height: 1; color: Theme.line }
                Text {
                    x: 16; y: 252; height: 26; verticalAlignment: Text.AlignVCenter; text: "可选英雄"
                    font.family: Theme.font; font.pixelSize: 18; font.bold: true; color: Theme.text
                }
                Text {
                    x: 108; y: 257; height: 20; verticalAlignment: Text.AlignVCenter; text: "按梯队排序"
                    font.family: Theme.font; font.pixelSize: 12; color: Theme.muted
                }
                Text {
                    x: 16; y: 284; width: 328; height: 60; visible: grid.count === 0
                    text: root.view.candidateEmpty || ""
                    horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                    font.family: Theme.font; font.pixelSize: 14; color: Theme.muted
                }
                GridView {
                    id: grid
                    objectName: "candidateGrid"
                    x: 12; y: 284; width: 336; height: 188
                    clip: true
                    cellWidth: 168; cellHeight: 64
                    boundsBehavior: Flickable.StopAtBounds
                    flickDeceleration: 3000
                    opacity: root.view.sourcePending ? .54 : 1
                    Behavior on opacity { OpacityAnimator { duration: Theme.ms(Theme.normal) } }
                    model: panel.candidateModel
                    delegate: CandidateCard {
                        cid: model.cid; name: model.name; tier: model.tier; portrait: model.portrait
                        selected: model.selected; tipText: model.tip; tip: tip
                    }
                    add: Transition {
                        OpacityAnimator { from: 0; to: 1; duration: Theme.ms(Theme.normal) }
                        ScaleAnimator { from: .92; to: 1; duration: Theme.ms(Theme.slow); easing.type: Easing.OutBack }
                    }
                    remove: Transition {
                        OpacityAnimator { to: 0; duration: Theme.ms(Theme.fast) }
                        ScaleAnimator { to: .92; duration: Theme.ms(Theme.fast) }
                    }
                    displaced: Transition {
                        XAnimator { duration: Theme.ms(Theme.slow); easing.type: Easing.OutCubic }
                        YAnimator { duration: Theme.ms(Theme.slow); easing.type: Easing.OutCubic }
                        OpacityAnimator { to: 1; duration: Theme.ms(Theme.fast) }
                        ScaleAnimator { to: 1; duration: Theme.ms(Theme.fast) }
                    }
                    move: Transition {
                        XAnimator { duration: Theme.ms(Theme.slow); easing.type: Easing.OutCubic }
                        YAnimator { duration: Theme.ms(Theme.slow); easing.type: Easing.OutCubic }
                    }
                    Rectangle {
                        visible: grid.contentHeight > grid.height
                        x: 332; width: 4; radius: 2; color: Theme.scrollThumb
                        y: grid.visibleArea.yPosition * grid.height
                        height: Math.max(24, grid.visibleArea.heightRatio * grid.height)
                    }
                }
            }

            // ---- GAME ----
            Item {
                visible: root.game
                width: 360; height: 580
                Text {
                    x: 14; y: 217; height: 26; verticalAlignment: Text.AlignVCenter; text: "海克斯推荐"
                    font.family: Theme.font; font.pixelSize: 17; font.bold: true; color: Theme.text
                    visible: !(root.view.cardStatus && !root.view.sourcePending)
                }
                Text {
                    x: 253; y: 220; width: 93; height: 20; visible: !root.view.cardStatus
                    text: root.view.recognized || ""; horizontalAlignment: Text.AlignRight
                    font.family: Theme.font; font.pixelSize: 12; color: Theme.muted
                }
                Text {
                    // Source switches report on the right; a failed read replaces the heading.
                    readonly property bool wide: !root.view.sourcePending
                    x: wide ? 14 : 174; y: 218; width: wide ? 335 : 171; height: 23
                    visible: !!root.view.cardStatus
                    text: root.view.cardStatus || ""
                    horizontalAlignment: wide ? Text.AlignLeft : Text.AlignRight; verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                    font.family: Theme.font; font.pixelSize: 12; color: Theme.muted
                }
                Item {
                    y: 244; width: 360; height: 126
                    opacity: root.view.sourcePending ? .54 : 1
                    Behavior on opacity { OpacityAnimator { duration: Theme.ms(Theme.normal) } }
                    Repeater {
                        objectName: "cardRepeater"
                        model: panel.cardModel
                        AugmentCard {
                            x: 14 + model.slot * 112
                            slot: model.slot; side: model.side; grade: model.grade; name: model.name
                            long: model.long; hint: model.hint; icon: model.icon; tipText: model.tip; key: model.key
                            tip: tip
                            onClicked: s => panel.correct(s)
                        }
                    }
                }
                Rectangle { x: 14; y: 382; width: 332; height: 1; color: Theme.line }
                Text {
                    x: 14; y: 389; height: 24; verticalAlignment: Text.AlignVCenter; text: "核心出装"
                    font.family: Theme.font; font.pixelSize: 17; font.bold: true; color: Theme.text
                }
                Text {
                    x: 117; y: 392; height: 20; verticalAlignment: Text.AlignVCenter; text: "英雄 / 模式推荐"
                    font.family: Theme.font; font.pixelSize: 11; color: Theme.muted
                }
                Repeater {
                    model: panel.itemModel
                    ItemTile {
                        x: 14 + model.slot * 86; y: 416
                        name: model.name; icon: model.icon; tipText: model.tip; tip: tip
                    }
                }
            }
        }
    }
    Rectangle {
        // Middle scroll position on a short work area.
        visible: body.interactive
        x: 350; width: 4; radius: 2; color: Theme.scrollThumb
        y: body.y + body.visibleArea.yPosition * body.height
        height: Math.max(24, body.visibleArea.heightRatio * body.height)
    }

    // ---- footer ----
    Item {
        y: root.height - (root.view.footer || 58)
        width: 360; height: root.view.footer || 58
        Item {
            visible: !root.game
            anchors.fill: parent
            Rectangle { x: 12; width: 336; height: 1; color: Theme.line }
            Text {
                x: 16; y: 9; width: 230; height: 20; verticalAlignment: Text.AlignVCenter
                text: root.view.caption || ""
                elide: Text.ElideRight
                font.family: Theme.font; font.pixelSize: 12; color: Theme.muted
                Hint { tip: tip; text: root.view.footerTip || "" }
            }
            PanelButton {
                x: 262; y: 4; width: 86; height: 28; radius: 8
                icon: "refresh"; text: root.view.refreshText || ""
                tip: tip; tipText: "刷新资料（" + (root.view.refreshKey || "") + "）"
                onClicked: panel.refresh()
            }
            Text {
                x: 135; y: 38; width: 90; height: 18
                text: root.view.toggleText || ""; horizontalAlignment: Text.AlignHCenter
                font.family: Theme.font; font.pixelSize: 11; color: toggleHover.hovered ? Theme.text : Theme.muted
                HoverHandler { id: toggleHover; cursorShape: Qt.PointingHandCursor }
                Hint { tip: tip; text: "收起海克斯随行" }
                TapHandler { onTapped: panel.collapse() }
            }
        }
        Item {
            visible: root.game
            anchors.fill: parent
            PanelButton {
                objectName: "scanButton"
                x: 60; y: 0; width: 180; height: 34; kind: "primary"
                icon: "scan"; text: root.view.scanText || ""; fontSize: 14
                spinning: root.view.scanning === true
                onClicked: panel.scan()
            }
            PanelButton {
                x: 250; y: 0; width: 36; height: 34; radius: 12; kind: "secondary"
                tip: tip; tipText: "刷新资料（" + (root.view.refreshKey || "") + "）"
                onClicked: panel.refresh()
                // Icon on top, the key underneath, as in the Tk panel.
                Icon { x: 11; y: root.view.refreshBadge ? 5 : 10; width: 14; height: 14; name: "refresh"; color: Theme.text }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter; y: 22
                    text: root.view.refreshBadge || ""
                    font.family: Theme.font; font.pixelSize: 9; color: Theme.muted
                }
            }
            Rectangle { x: 14; y: 38; width: 332; height: 1; color: Theme.line }
            Text {
                x: 14; y: 41; width: 246; height: 14; verticalAlignment: Text.AlignVCenter
                text: root.view.caption || ""; elide: Text.ElideRight
                font.family: Theme.font; font.pixelSize: 10; color: Theme.muted
                Hint { tip: tip; text: root.view.footerTip || "" }
            }
            Text {
                x: 280; y: 41; width: 66; height: 14; verticalAlignment: Text.AlignVCenter
                text: root.view.toggleText || ""; horizontalAlignment: Text.AlignRight
                font.family: Theme.font; font.pixelSize: 10; color: gameToggle.hovered ? Theme.text : Theme.muted
                HoverHandler { id: gameToggle; cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: panel.collapse() }
            }
        }
    }

    // ---- bottom-right resize grip: scales everything, the window keeps its top-left ----
    Item {
        x: root.width - 14; y: root.height - 14; width: 14; height: 14
        property real startZoom: 1
        property point start
        HoverHandler { cursorShape: Qt.SizeFDiagCursor }
        DragHandler {
            target: null
            onActiveChanged: {
                if (active) { parent.startZoom = panel.place.zoom; parent.start = centroid.scenePosition }
                else panel.resized()
            }
            onCentroidChanged: {
                if (!active) return
                const dx = centroid.scenePosition.x - parent.start.x, dy = centroid.scenePosition.y - parent.start.y
                const h = root.view.baseHeight || 540
                panel.resize(parent.startZoom + (dx * 360 + dy * h) / (360 * 360 + h * h))
            }
        }
    }

    Tip { id: tip }
}

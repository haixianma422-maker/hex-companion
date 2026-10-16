import QtQuick
import QtQuick.Effects

// SELECT panel at the V2 handoff's logical coordinates (360×540).
Rectangle {
    id: panel
    width: 360; height: 540
    radius: 14
    color: Theme.bg
    readonly property var view: bridge.view

    // ---- hero transition: fade-through, never a cross-blend of two names ----
    property var shown: ({ heroId: 0, heroName: "", heroTitle: "", heroTier: "—", splash: "", focusX: .72, focusY: .42 })
    function adopt() {
        shown = { heroId: view.heroId, heroName: view.heroName, heroTitle: view.heroTitle,
                  heroTier: view.heroTier, splash: view.splash, focusX: view.focusX, focusY: view.focusY }
    }
    Component.onCompleted: adopt()
    Connections {
        target: bridge
        function onViewChanged() {
            if (panel.view.heroId !== panel.shown.heroId && panel.shown.heroId !== 0) heroSwap.restart()
            else if (!heroSwap.running) panel.adopt()       // same hero: images or data finished loading
        }
    }
    SequentialAnimation {
        id: heroSwap
        ParallelAnimation {
            OpacityAnimator { target: heroContent; to: 0; duration: 110; easing.type: Easing.InCubic }
            XAnimator { target: heroContent; to: -8; duration: 110; easing.type: Easing.InCubic }
        }
        ScriptAction { script: panel.adopt() }
        PropertyAction { target: heroContent; property: "x"; value: 12 }
        ParallelAnimation {
            OpacityAnimator { target: heroContent; to: 1; duration: 240; easing.type: Easing.OutCubic }
            XAnimator { target: heroContent; to: 0; duration: 280; easing.type: Easing.OutQuint }
        }
    }

    // ---- header ----
    Brand { x: 16; y: 10; width: 20; height: 20 }
    Text {
        x: 45; y: 8; height: 24; text: "海克斯随行"
        verticalAlignment: Text.AlignVCenter
        font.family: Theme.font; font.pixelSize: 17; font.bold: true; color: Theme.text
    }
    Repeater {
        model: [{ icon: "minus", x: 287, act: "collapse" }, { icon: "settings", x: 321, act: "settings" }]
        Rectangle {
            x: modelData.x; y: 4; width: 28; height: 28; radius: 8
            color: iconHover.hovered ? Theme.raised : "transparent"
            Behavior on color { ColorAnimation { duration: Theme.fast } }
            Icon { anchors.centerIn: parent; name: modelData.icon; color: Theme.muted; width: 16; height: 16 }
            HoverHandler { id: iconHover; cursorShape: Qt.PointingHandCursor }
            TapHandler { onTapped: if (modelData.act === "collapse") bridge.collapse() }
        }
    }
    Rectangle { x: 12; y: 38; width: 336; height: 1; color: Theme.line }

    Rectangle {
        id: statusDot
        x: 16; y: 55; width: 8; height: 8; radius: 4; color: Theme.accent
        SequentialAnimation {
            running: panel.view.loading; loops: Animation.Infinite
            alwaysRunToEnd: true
            OpacityAnimator { target: statusDot; to: .35; duration: 520; easing.type: Easing.InOutSine }
            OpacityAnimator { target: statusDot; to: 1; duration: 520; easing.type: Easing.InOutSine }
        }
    }
    Text {
        x: 32; y: 48; height: 22; verticalAlignment: Text.AlignVCenter
        text: panel.view.stage === "game" ? "对局中" : panel.view.stage === "select" ? "选人中" : "等待连接"
        font.family: Theme.font; font.pixelSize: 13; font.bold: true; color: Theme.text
    }
    SourceSwitch {
        x: 236; y: 46
        value: panel.view.source
        onChosen: source => bridge.selectSource(source)
    }

    // ---- hero ----
    Item {
        id: heroBox
        x: 6; y: 75; width: 348; height: 106
        Item {
            id: heroArt
            anchors.fill: parent
            layer.enabled: true
            layer.effect: MultiEffect { maskEnabled: true; maskSource: heroMask }
            Rectangle { anchors.fill: parent; color: Theme.lilac }
            Splash {
                anchors.fill: parent
                focusX: panel.shown.focusX; focusY: panel.shown.focusY
                source: panel.shown.splash
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
        }
        Item {
            id: heroMask
            anchors.fill: parent; visible: false; layer.enabled: true
            Rectangle { anchors.fill: parent; radius: 8 }
        }
        Item {
            id: heroContent
            width: parent.width; height: parent.height
            Text {
                id: heroName
                x: 14; y: 21; height: 44; width: 170
                text: panel.shown.heroName
                fontSizeMode: Text.HorizontalFit; minimumPixelSize: 24
                verticalAlignment: Text.AlignVCenter
                font.family: Theme.font; font.pixelSize: 34; font.bold: true; color: Theme.ink
            }
            Rectangle {
                x: heroName.x + heroName.contentWidth + 8; y: 35; width: 30; height: 22; radius: 11
                color: Theme.tierPill
                Text {
                    anchors.centerIn: parent; text: panel.shown.heroTier
                    font.family: Theme.font; font.pixelSize: 14; font.bold: true; color: Theme.ink
                }
            }
            Text {
                x: 14; y: 70; height: 24; width: 180
                text: panel.shown.heroTitle
                elide: Text.ElideRight
                font.family: Theme.font; font.pixelSize: 15; font.bold: true; color: Theme.inkMuted
            }
        }
    }

    // ---- summoner spells ----
    Item {
        id: advice
        x: 0; y: 191; width: 360; height: 44
        opacity: panel.view.loading && panel.view.spells.length === 0 ? .45 : 1
        Behavior on opacity { OpacityAnimator { duration: Theme.normal } }
        Text {
            x: 16; y: 10; height: 22; verticalAlignment: Text.AlignVCenter; text: "召唤师技能"
            font.family: Theme.font; font.pixelSize: 14; font.bold: true; color: Theme.text
        }
        Text {
            x: 102; y: 4; width: 151; height: 32
            visible: panel.view.spells.length !== 2
            text: "暂无推荐"; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
            font.family: Theme.font; font.pixelSize: 12; color: Theme.text
        }
        Repeater {
            model: panel.view.spells.length === 2 ? panel.view.spells : []
            Item {
                x: 102 + index * 86; y: 4; width: 80; height: 32
                Rectangle {
                    width: 32; height: 32; radius: 6; color: Theme.surface; border.color: "#645775"
                    Image {
                        id: spellIcon
                        anchors.fill: parent; anchors.margins: 1
                        source: modelData.icon; asynchronous: true; sourceSize: Qt.size(64, 64)
                        opacity: status === Image.Ready ? 1 : 0
                        Behavior on opacity { OpacityAnimator { duration: Theme.normal } }
                    }
                }
                Text {
                    x: 37; y: 6; height: 20; verticalAlignment: Text.AlignVCenter
                    text: modelData.name
                    font.family: Theme.font; font.pixelSize: 12; color: Theme.text
                }
            }
        }
        Text {
            x: 170; y: 11; width: 12; height: 20; visible: panel.view.spells.length === 2
            text: "+"; horizontalAlignment: Text.AlignHCenter
            font.family: Theme.font; font.pixelSize: 12; color: Theme.muted
        }
        Text {
            x: 270; y: 12; width: 74; height: 18; visible: panel.view.spellSupplement
            text: "OP.GG 补充"; horizontalAlignment: Text.AlignRight
            font.family: Theme.font; font.pixelSize: 10; color: Theme.muted
        }
    }

    // ---- candidates ----
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
        x: 16; y: 284; width: 328; height: 60
        visible: grid.count === 0
        text: panel.view.stage === "game" ? "对局中 · 样例只验证浮窗叠加" : "等待客户端返回候选英雄"
        horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
        font.family: Theme.font; font.pixelSize: 14; color: Theme.muted
    }
    GridView {
        id: grid
        x: 12; y: 284; width: 336; height: 188
        clip: true
        cellWidth: 168; cellHeight: 64
        boundsBehavior: Flickable.StopAtBounds
        flickDeceleration: 3000
        model: bridge.candidateModel
        delegate: CandidateCard {
            cid: model.cid; name: model.name; title: model.title; tier: model.tier
            portrait: model.portrait; selected: model.selected
            onPicked: id => bridge.pick(id)
        }
        add: Transition {
            OpacityAnimator { from: 0; to: 1; duration: Theme.normal }
            ScaleAnimator { from: .92; to: 1; duration: Theme.slow; easing.type: Easing.OutBack }
        }
        remove: Transition {
            OpacityAnimator { to: 0; duration: Theme.fast }
            ScaleAnimator { to: .92; duration: Theme.fast }
        }
        displaced: Transition {
            XAnimator { duration: Theme.slow; easing.type: Easing.OutCubic }
            YAnimator { duration: Theme.slow; easing.type: Easing.OutCubic }
            OpacityAnimator { to: 1; duration: Theme.fast }
            ScaleAnimator { to: 1; duration: Theme.fast }
        }
        move: Transition {
            XAnimator { duration: Theme.slow; easing.type: Easing.OutCubic }
            YAnimator { duration: Theme.slow; easing.type: Easing.OutCubic }
        }
        Rectangle {
            visible: grid.contentHeight > grid.height
            x: 332; width: 4; radius: 2; color: "#665974"
            y: grid.visibleArea.yPosition * grid.height
            height: Math.max(24, grid.visibleArea.heightRatio * grid.height)
            opacity: grid.moving ? 1 : .6
            Behavior on opacity { OpacityAnimator { duration: Theme.normal } }
        }
    }

    // ---- footer ----
    Rectangle { x: 12; y: 482; width: 336; height: 1; color: Theme.line }
    Text {
        x: 16; y: 491; width: 230; height: 20; verticalAlignment: Text.AlignVCenter
        text: panel.view.error ? "操作未完成，保留缓存 · " + panel.view.error : panel.view.caption
        elide: Text.ElideRight
        font.family: Theme.font; font.pixelSize: 12; color: Theme.muted
    }
    Rectangle {
        x: 262; y: 486; width: 86; height: 28; radius: 8
        color: refreshHover.hovered ? Theme.raised : "transparent"
        Behavior on color { ColorAnimation { duration: Theme.fast } }
        Icon {
            id: refreshIcon
            x: 6; y: 6; width: 16; height: 16; name: "refresh"; color: Theme.muted
            RotationAnimator on rotation {
                running: panel.view.loading; loops: Animation.Infinite
                from: 0; to: 360; duration: 900; alwaysRunToEnd: true
            }
        }
        Text {
            x: 27; y: 3; height: 22; verticalAlignment: Text.AlignVCenter
            text: "刷新 " + panel.view.refreshKey
            font.family: Theme.font; font.pixelSize: 12; color: Theme.muted
        }
        HoverHandler { id: refreshHover; cursorShape: Qt.PointingHandCursor }
        TapHandler { onTapped: bridge.refresh() }
    }
    Text {
        x: 135; y: 518; width: 90; height: 18
        text: panel.view.toggleKey + " 收起"; horizontalAlignment: Text.AlignHCenter
        font.family: Theme.font; font.pixelSize: 11; color: collapseHover.hovered ? Theme.text : Theme.muted
        HoverHandler { id: collapseHover; cursorShape: Qt.PointingHandCursor }
        TapHandler { onTapped: bridge.collapse() }
    }
}

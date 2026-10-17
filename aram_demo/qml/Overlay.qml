import QtQuick
import QtQuick.Effects

// The overlay's native windows: the panel, its click-through shadow and the collapsed bubble.
// All are tool windows that never take focus from the League client or the game.
QtObject {
    id: overlay
    readonly property int margin: 16
    readonly property int flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                                 | Qt.WindowDoesNotAcceptFocus | Qt.NoDropShadowWindowHint
    property Binding motion: Binding { target: Theme; property: "motion"; value: panel.animated }

    property Window shadowWindow: Window {
        // WindowTransparentForInput sets WS_EX_TRANSPARENT: clicks on the shadow reach the game.
        id: shadowWindow
        objectName: "shadowWindow"
        title: "海克斯随行 · 阴影"
        flags: overlay.flags | Qt.WindowTransparentForInput
        color: "transparent"
        x: panelWindow.x - overlay.margin; y: panelWindow.y - overlay.margin
        width: panelWindow.width + 2 * overlay.margin; height: panelWindow.height + 2 * overlay.margin
        visible: false
        Item {
            id: shadowBody
            x: overlay.margin; y: overlay.margin + 10
            width: panelWindow.width; height: panelWindow.height
            opacity: 0; scale: .94
            transformOrigin: Item.BottomRight
            RectangularShadow {
                anchors.fill: parent
                radius: 14 * panel.place.zoom; blur: 16; offset.y: 5
                color: Qt.rgba(0, 0, 0, .42)
            }
        }
    }

    property Window panelWindow: Window {
        id: panelWindow
        objectName: "panelWindow"
        title: "海克斯随行 · 伴随浮窗"
        flags: overlay.flags
        color: "transparent"
        transientParent: shadowWindow           // an owned window stays above its owner
        x: panel.place.x; y: panel.place.y
        width: panel.place.width; height: panel.place.height
        visible: false

        Connections {
            target: panel
            function onShownChanged() {
                if (panel.shown) showPanel.restart()
                else if (panel.animateHide) hidePanel.restart()
                else { showPanel.stop(); hidePanel.stop(); panelWindow.visible = false; shadowWindow.visible = false; panel.hidden() }
            }
        }
        Component.onCompleted: if (panel.shown) showPanel.restart()

        // Animators run on the render thread, so Python work on the GUI thread cannot stall them.
        SequentialAnimation {
            id: showPanel
            ScriptAction { script: { hidePanel.stop(); shadowWindow.visible = true; panelWindow.visible = true } }
            ParallelAnimation {
                OpacityAnimator { target: surface; to: 1; duration: Theme.ms(220); easing.type: Easing.OutCubic }
                OpacityAnimator { target: shadowBody; to: 1; duration: Theme.ms(220); easing.type: Easing.OutCubic }
                ScaleAnimator { target: surface; to: 1; duration: Theme.ms(320); easing.type: Easing.OutQuint }
                ScaleAnimator { target: shadowBody; to: 1; duration: Theme.ms(320); easing.type: Easing.OutQuint }
                YAnimator { target: surface; to: 0; duration: Theme.ms(320); easing.type: Easing.OutQuint }
                YAnimator { target: shadowBody; to: overlay.margin; duration: Theme.ms(320); easing.type: Easing.OutQuint }
            }
        }
        SequentialAnimation {
            id: hidePanel
            ScriptAction { script: showPanel.stop() }
            ParallelAnimation {
                OpacityAnimator { target: surface; to: 0; duration: Theme.ms(180); easing.type: Easing.InCubic }
                OpacityAnimator { target: shadowBody; to: 0; duration: Theme.ms(180); easing.type: Easing.InCubic }
                ScaleAnimator { target: surface; to: .86; duration: Theme.ms(200); easing.type: Easing.InCubic }
                ScaleAnimator { target: shadowBody; to: .86; duration: Theme.ms(200); easing.type: Easing.InCubic }
                YAnimator { target: surface; to: 14; duration: Theme.ms(200); easing.type: Easing.InCubic }
                YAnimator { target: shadowBody; to: overlay.margin + 14; duration: Theme.ms(200); easing.type: Easing.InCubic }
            }
            ScriptAction { script: { panelWindow.visible = false; shadowWindow.visible = false; panel.hidden() } }
        }

        Item {
            id: surface
            objectName: "panelSurface"
            y: 10; width: panelWindow.width; height: panelWindow.height
            opacity: 0; scale: .94
            transformOrigin: Item.BottomRight     // collapse heads for the bubble at the bottom-right
            Item {
                scale: panel.place.zoom
                transformOrigin: Item.TopLeft
                Panel { id: content; height: panelWindow.height / panel.place.zoom }
            }
        }

        // Report where the user dropped the panel, so re-anchoring keeps the offset.
        property real lastX: x
        property real lastY: y
        onXChanged: settle.restart()
        onYChanged: settle.restart()
        property Timer settle: Timer {
            interval: 250
            onTriggered: if (panelWindow.visible && (panelWindow.x !== panel.place.x || panelWindow.y !== panel.place.y))
                             panel.moved(panelWindow.x, panelWindow.y)
        }
    }

    property Window bubbleWindow: Window {
        id: bubbleWindow
        objectName: "bubbleWindow"
        title: "海克斯随行 · 浮标"
        flags: overlay.flags
        color: "transparent"
        x: bubble.state.x; y: bubble.state.y
        width: bubble.state.size; height: bubble.state.size
        visible: false

        Connections {
            target: bubble
            function onChanged() {
                if (bubble.state.shown && !bubbleWindow.visible) showBubble.restart()
                else if (!bubble.state.shown && bubbleWindow.visible && !hideBubble.running)
                    bubble.state.animateHide ? hideBubble.restart() : bubbleWindow.visible = false
            }
        }
        SequentialAnimation {
            id: showBubble
            ScriptAction { script: { hideBubble.stop(); bubbleWindow.visible = true } }
            PauseAnimation { duration: Theme.ms(120) }      // let the panel start folding first
            ParallelAnimation {
                OpacityAnimator { target: face; to: 1; duration: Theme.ms(180) }
                ScaleAnimator { target: face; to: 1; duration: Theme.ms(340); easing.type: Easing.OutBack; easing.overshoot: 2.2 }
            }
        }
        SequentialAnimation {
            id: hideBubble
            ScriptAction { script: showBubble.stop() }
            ParallelAnimation {
                OpacityAnimator { target: face; to: 0; duration: Theme.ms(140) }
                ScaleAnimator { target: face; to: .7; duration: Theme.ms(140) }
            }
            ScriptAction { script: bubbleWindow.visible = false }
        }

        Rectangle {
            id: face
            anchors.fill: parent
            radius: width / 2
            color: tap.pressed ? Theme.bg : hover.hovered ? Theme.raised : Theme.surface
            border.color: Theme.line
            opacity: 0; scale: .6
            Behavior on color { ColorAnimation { duration: Theme.ms(Theme.fast) } }
            Brand { anchors.centerIn: parent; width: parent.width * .55; height: parent.height * .55 }
            HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
            TapHandler { id: tap; onTapped: bubble.expand() }
            DragHandler {
                target: null
                onActiveChanged: if (active) bubbleWindow.startSystemMove()
            }
        }
        onXChanged: bubbleSettle.restart()
        onYChanged: bubbleSettle.restart()
        property Timer bubbleSettle: Timer {
            interval: 250
            onTriggered: if (bubbleWindow.visible && (bubbleWindow.x !== bubble.state.x || bubbleWindow.y !== bubble.state.y))
                             bubble.moved(bubbleWindow.x, bubbleWindow.y)
        }
    }
}

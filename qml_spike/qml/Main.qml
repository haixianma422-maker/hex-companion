import QtQuick
import QtQuick.Effects

// Native windows like the Tk app: the panel, its click-through shadow and the collapsed bubble.
// All are tool windows that never take focus away from the League client or game.
QtObject {
    id: app
    readonly property int margin: 16            // shadow spread, drawn in its own click-through window
    readonly property var view: bridge.view
    readonly property bool panelWanted: view.visible && !view.collapsed && view.stage !== "hidden"
    readonly property bool bubbleWanted: view.visible && view.collapsed && view.stage !== "hidden"
    readonly property int overlayFlags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                                        | Qt.WindowDoesNotAcceptFocus | Qt.NoDropShadowWindowHint

    property Window panelWindow: Window {
        id: panelWindow
        objectName: "panelWindow"
        title: "海克斯随行 · QML 样例"
        flags: app.overlayFlags
        color: "transparent"
        width: 360; height: 540
        x: bridge.geometry.x
        y: bridge.geometry.y
        visible: false
        transientParent: shadowWindow          // owned windows stay above their owner

        property bool shown: app.panelWanted
        onShownChanged: shown ? showPanel.restart() : hidePanel.restart()
        Component.onCompleted: if (shown) showPanel.restart()

        // Animators run on the render thread, so a busy Python GUI thread cannot stall them.
        // The shadow lives in another window and gets its own animators in the same group.
        SequentialAnimation {
            id: showPanel
            ScriptAction { script: { hidePanel.stop(); shadowWindow.visible = true; panelWindow.visible = true } }
            ParallelAnimation {
                OpacityAnimator { target: surface; to: 1; duration: 220; easing.type: Easing.OutCubic }
                OpacityAnimator { target: shadowBody; to: 1; duration: 220; easing.type: Easing.OutCubic }
                ScaleAnimator { target: surface; to: 1; duration: 320; easing.type: Easing.OutQuint }
                ScaleAnimator { target: shadowBody; to: 1; duration: 320; easing.type: Easing.OutQuint }
                YAnimator { target: surface; to: 0; duration: 320; easing.type: Easing.OutQuint }
                YAnimator { target: shadowBody; to: app.margin; duration: 320; easing.type: Easing.OutQuint }
            }
        }
        SequentialAnimation {
            id: hidePanel
            ScriptAction { script: showPanel.stop() }
            ParallelAnimation {
                OpacityAnimator { target: surface; to: 0; duration: 180; easing.type: Easing.InCubic }
                OpacityAnimator { target: shadowBody; to: 0; duration: 180; easing.type: Easing.InCubic }
                ScaleAnimator { target: surface; to: .86; duration: 200; easing.type: Easing.InCubic }
                ScaleAnimator { target: shadowBody; to: .86; duration: 200; easing.type: Easing.InCubic }
                YAnimator { target: surface; to: 14; duration: 200; easing.type: Easing.InCubic }
                YAnimator { target: shadowBody; to: app.margin + 14; duration: 200; easing.type: Easing.InCubic }
            }
            ScriptAction { script: { panelWindow.visible = false; shadowWindow.visible = false } }
        }

        Item {
            id: surface
            x: 0; y: 10; width: 360; height: 540
            opacity: 0; scale: .94
            // Collapse heads for the bubble, which sits at the panel's bottom-right.
            transformOrigin: Item.BottomRight

            Panel { id: panelContent }

            // Window drag from the header strip; the system move keeps the cursor glued.
            Item {
                x: 0; y: 0; width: 280; height: 38
                DragHandler {
                    target: null
                    onActiveChanged: if (active) { panelWindow.startSystemMove(); dragWatch.begin() }
                }
            }
            Text {
                visible: hud !== null
                anchors { right: parent.right; bottom: parent.bottom; margins: 4 }
                text: hud ? hud.text : ""
                font.pixelSize: 10; font.family: "Consolas"; color: "#7f7"
            }
        }

        // Records where the user dropped the panel, so later re-anchoring keeps the offset.
        property QtObject dragWatch: QtObject {
            id: dragWatch
            property real startX; property real startY
            function begin() { startX = panelWindow.x; startY = panelWindow.y; settle.restart() }
            property Timer settle: Timer {
                interval: 250; repeat: true
                onTriggered: {
                    const dx = panelWindow.x - dragWatch.startX, dy = panelWindow.y - dragWatch.startY
                    if (dx !== 0 || dy !== 0) { bridge.moved(dx, dy); dragWatch.startX = panelWindow.x; dragWatch.startY = panelWindow.y }
                    else stop()
                }
            }
        }
    }

    // WindowTransparentForInput sets WS_EX_TRANSPARENT: clicks on the shadow reach the game below.
    property Window shadowWindow: Window {
        id: shadowWindow
        objectName: "shadowWindow"
        title: "海克斯随行 · 阴影"
        flags: app.overlayFlags | Qt.WindowTransparentForInput
        color: "transparent"
        width: 360 + 2 * app.margin; height: 540 + 2 * app.margin
        x: panelWindow.x - app.margin
        y: panelWindow.y - app.margin
        visible: false
        Item {
            id: shadowBody
            x: app.margin; y: app.margin + 10; width: 360; height: 540
            opacity: 0; scale: .94
            transformOrigin: Item.BottomRight
            RectangularShadow {
                anchors.fill: parent
                radius: 14; blur: 16; spread: 0; offset.y: 5
                color: Qt.rgba(0, 0, 0, .42)
            }
        }
    }

    property Window bubbleWindow: Window {
        id: bubbleWindow
        objectName: "bubbleWindow"
        title: "海克斯随行 · 浮标"
        flags: app.overlayFlags
        color: "transparent"
        width: 48 + 16; height: 48 + 16
        x: panelWindow.x + 360 - 48 - 8
        y: panelWindow.y + 540 - 48 - 8
        visible: false

        property bool shown: app.bubbleWanted
        onShownChanged: shown ? showBubble.restart() : hideBubble.restart()

        SequentialAnimation {
            id: showBubble
            ScriptAction { script: { hideBubble.stop(); bubbleWindow.visible = true } }
            PauseAnimation { duration: 120 }        // let the panel start folding first
            ParallelAnimation {
                OpacityAnimator { target: bubble; to: 1; duration: 180 }
                ScaleAnimator { target: bubble; to: 1; duration: 340; easing.type: Easing.OutBack; easing.overshoot: 2.2 }
                YAnimator { target: bubble; to: 8; duration: 260; easing.type: Easing.OutCubic }
            }
        }
        SequentialAnimation {
            id: hideBubble
            ScriptAction { script: showBubble.stop() }
            ParallelAnimation {
                OpacityAnimator { target: bubble; to: 0; duration: 140 }
                ScaleAnimator { target: bubble; to: .7; duration: 140 }
            }
            ScriptAction { script: { bubbleWindow.visible = false; bubble.y = 16 } }
        }

        Rectangle {
            id: bubble
            x: 8; y: 16; width: 48; height: 48; radius: 24
            color: bubbleHover.hovered ? Theme.raised : Theme.surface
            border.color: Theme.line
            opacity: 0; scale: .6
            Behavior on color { ColorAnimation { duration: Theme.fast } }
            Brand { anchors.centerIn: parent; width: 24; height: 24 }
            HoverHandler { id: bubbleHover; cursorShape: Qt.PointingHandCursor }
            TapHandler { onTapped: bridge.expand() }
            DragHandler { target: null; onActiveChanged: if (active) bubbleWindow.startSystemMove() }
        }
    }
}

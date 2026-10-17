import QtQuick

// Hover hint inside the panel window; the Tk panel showed the same texts after 450 ms.
Rectangle {
    id: tip
    property Item owner: null
    property string text: ""
    property point at
    visible: opacity > 0
    opacity: 0
    z: 100
    color: Theme.surface
    border.color: Theme.line
    radius: 8
    width: Math.min(260, label.implicitWidth + 18)
    height: label.implicitHeight + 12
    x: Math.max(4, Math.min(parent.width - width - 4, at.x))
    y: at.y + height + 24 > parent.height ? at.y - height - 8 : at.y + 20
    Behavior on opacity { OpacityAnimator { duration: Theme.ms(Theme.fast) } }

    Text {
        id: label
        x: 9; y: 6
        width: Math.min(242, implicitWidth)
        text: tip.text
        wrapMode: Text.Wrap
        font.family: Theme.font; font.pixelSize: 12; color: Theme.text
    }

    Timer { id: delay; interval: 450; onTriggered: tip.opacity = 1 }

    // Owners call this from a HoverHandler: hover(item, text, hovered, point in tip's parent).
    function hover(item, value, hovered, point) {
        if (hovered && value) {
            if (owner !== item) { opacity = 0; owner = item }
            text = value; at = point; delay.restart()
        } else if (owner === item) {
            delay.stop(); opacity = 0; owner = null
        }
    }
}

import QtQuick

// Two-option source picker; the thumb springs to the chosen side.
Rectangle {
    id: root
    property string value: "opgg"
    signal chosen(string source)
    readonly property var options: [{ key: "opgg", label: "OP.GG" }, { key: "qq101", label: "101" }]
    readonly property int index: value === "qq101" ? 1 : 0
    width: 112; height: 26; radius: 13
    color: Theme.raised

    Rectangle {
        id: thumb
        y: 2; width: root.width / 2 - 2; height: root.height - 4; radius: height / 2
        x: 2 + root.index * (root.width / 2 - 2)
        color: Theme.accent
        Behavior on x { XAnimator { duration: 260; easing.type: Easing.OutBack; easing.overshoot: 1.4 } }
    }
    Row {
        anchors.fill: parent
        Repeater {
            model: root.options
            Item {
                width: root.width / 2; height: root.height
                Text {
                    anchors.centerIn: parent
                    text: modelData.label
                    font.family: Theme.font; font.pixelSize: 12; font.bold: true
                    color: index === root.index ? Theme.ink : (hover.hovered ? Theme.text : Theme.muted)
                    Behavior on color { ColorAnimation { duration: Theme.fast } }
                }
                HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: if (modelData.key !== root.value) root.chosen(modelData.key) }
            }
        }
    }
}

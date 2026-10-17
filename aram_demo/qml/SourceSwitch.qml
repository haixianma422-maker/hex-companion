import QtQuick

// OP.GG / 101 picker. It shows the active source and only reports a choice; the switch
// moves when CompanionApp has actually changed source.
Rectangle {
    id: root
    property string value: "opgg"
    property var labels: ["OP.GG", "101"]
    property int fontSize: 12
    signal chosen(string source)
    readonly property var keys: ["opgg", "qq101"]
    readonly property int index: value === "qq101" ? 1 : 0
    width: 112; height: 26; radius: height / 2
    color: Theme.raised

    Rectangle {
        y: 2; width: root.width / 2 - 2; height: root.height - 4; radius: height / 2
        x: 2 + root.index * (root.width / 2 - 2)
        color: Theme.accent
        Behavior on x { XAnimator { duration: Theme.ms(260); easing.type: Easing.OutBack; easing.overshoot: 1.4 } }
    }
    Row {
        anchors.fill: parent
        Repeater {
            model: 2
            Item {
                width: root.width / 2; height: root.height
                Text {
                    anchors.centerIn: parent
                    text: root.labels[index]
                    font.family: Theme.font; font.pixelSize: root.fontSize; font.bold: true
                    color: index === root.index ? Theme.ink : (hover.hovered ? Theme.text : Theme.muted)
                    Behavior on color { ColorAnimation { duration: Theme.ms(Theme.fast) } }
                }
                HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: if (root.keys[index] !== root.value) root.chosen(root.keys[index]) }
            }
        }
    }
}

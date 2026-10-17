import QtQuick

// Flat panel button: ghost (header icons), primary (scan) or secondary (refresh).
Rectangle {
    id: button
    property string kind: "ghost"
    property string icon: ""
    property string text: ""
    property color iconColor: kind === "primary" ? Theme.ink : Theme.muted
    property color textColor: kind === "primary" ? Theme.ink : Theme.muted
    property int fontSize: 12
    property bool spinning: false
    property string tipText: ""
    property Item tip: null
    signal clicked()

    readonly property color base: kind === "primary" ? Theme.accent : kind === "secondary" ? Theme.raised : "transparent"
    readonly property color over: kind === "primary" ? Theme.accentHover : kind === "secondary" ? "#4B405C" : Theme.raised
    radius: height / 2
    color: hover.hovered ? over : base
    scale: tap.pressed ? .96 : 1
    Behavior on color { ColorAnimation { duration: Theme.ms(Theme.fast) } }
    Behavior on scale { ScaleAnimator { duration: Theme.ms(90) } }

    Row {
        anchors.centerIn: parent
        spacing: 7
        Icon {
            id: glyph
            visible: button.icon !== ""
            name: button.icon
            color: button.iconColor
            width: 16; height: 16
            anchors.verticalCenter: parent.verticalCenter
            RotationAnimator on rotation {
                running: button.spinning && Theme.motion
                loops: Animation.Infinite; from: 0; to: 360; duration: 900
            }
        }
        Text {
            visible: button.text !== ""
            text: button.text
            anchors.verticalCenter: parent.verticalCenter
            font.family: Theme.font; font.pixelSize: button.fontSize; font.bold: button.kind === "primary"
            color: button.textColor
        }
    }
    HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
    Hint { tip: button.tip; text: button.tipText }
    TapHandler { id: tap; onTapped: button.clicked() }
}

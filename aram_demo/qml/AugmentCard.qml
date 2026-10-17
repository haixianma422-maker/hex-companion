import QtQuick

// One recognised augment (108×126). Colour follows the grade; a click opens manual correction.
// Only a card whose result changed replays its reveal.
Rectangle {
    id: card
    property int slot
    property string side
    property string grade: "—"
    property string name
    property bool long
    property string hint
    property string icon
    property string tipText
    property string key
    property Item tip: null
    signal clicked(int slot)
    width: 108; height: 126; radius: 10
    color: Theme.gradeColors[grade] || Theme.gradeColors["—"]
    Behavior on color { ColorAnimation { duration: Theme.ms(Theme.slow) } }
    scale: tap.pressed ? .97 : 1
    Behavior on scale { ScaleAnimator { duration: Theme.ms(90) } }

    onKeyChanged: reveal.restart()
    SequentialAnimation {
        id: reveal
        PropertyAction { target: content; property: "opacity"; value: .2 }
        PropertyAction { target: content; property: "y"; value: 4 }
        ParallelAnimation {
            OpacityAnimator { target: content; to: 1; duration: Theme.ms(180); easing.type: Easing.OutCubic }
            YAnimator { target: content; to: 0; duration: Theme.ms(220); easing.type: Easing.OutCubic }
        }
    }

    Item {
        id: content
        width: card.width; height: card.height
        Text {
            x: 6; y: 6; width: 96; height: 18
            text: card.side; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
            font.family: Theme.font; font.pixelSize: 11; color: Theme.ink
        }
        Icon { visible: card.grade === "S"; name: "star"; x: 90; y: 7; width: 10; height: 12; color: Theme.ink }
        Text {
            x: 10; y: 25; width: 52; height: 61
            text: card.grade; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
            font.family: Theme.font; font.pixelSize: 52; font.bold: true; color: Theme.ink
        }
        Item {
            x: 62; y: 31; width: 38; height: 38
            Icon { anchors.fill: parent; visible: !art.ready; name: "question"; color: Theme.ink; stroke: 1.6 }
            RoundImage { id: art; anchors.fill: parent; source: card.icon; radius: 0; fillMode: Image.PreserveAspectFit }
        }
        Text {
            x: 6; y: card.long ? 75 : 77; width: 96; height: card.long ? 34 : 22
            text: card.name
            horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
            wrapMode: Text.Wrap; maximumLineCount: card.long ? 2 : 1; elide: Text.ElideRight
            lineHeight: card.long ? 17 : 22; lineHeightMode: Text.FixedHeight
            font.family: Theme.font; font.pixelSize: card.long ? 12 : 14; font.bold: true; color: Theme.ink
        }
        Text {
            x: 6; y: card.long ? 109 : 104; width: 96; height: card.long ? 16 : 18
            text: card.hint; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
            font.family: Theme.font; font.pixelSize: 11; color: Theme.ink
        }
    }
    HoverHandler { cursorShape: Qt.PointingHandCursor }
    Hint { tip: card.tip; text: card.tipText }
    TapHandler { id: tap; onTapped: card.clicked(card.slot) }
}

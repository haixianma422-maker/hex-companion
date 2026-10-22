import QtQuick

// One candidate cell (not clickable, as in the Tk panel). Hover shows its hint; selection animates.
Item {
    id: card
    objectName: "candidateCard"
    property int cid
    property string name
    property string tier
    property string portrait
    property bool selected
    property string tipText
    property Item tip: null
    property bool revealed: false
    width: 164; height: 60
    Component.onCompleted: revealed = true

    Rectangle {
        objectName: "candidateBody"
        anchors.fill: parent
        // The card fades itself in. Grid transitions interrupt one another, so they only move cards.
        opacity: card.revealed ? 1 : 0
        scale: card.revealed ? 1 : .92
        Behavior on opacity { NumberAnimation { duration: Theme.ms(Theme.normal) } }
        Behavior on scale { NumberAnimation { duration: Theme.ms(Theme.slow); easing.type: Easing.OutBack } }
        radius: 10
        color: card.selected ? Theme.lilac : (hover.hovered ? Theme.hover : Theme.surface)
        Behavior on color { ColorAnimation { duration: Theme.ms(Theme.normal); easing.type: Easing.OutCubic } }

        Rectangle {
            x: 4; y: 26; width: 7; height: 7; radius: 3.5
            color: Theme.accent; border.color: Theme.ink; border.width: 1
            scale: card.selected ? 1 : 0
            Behavior on scale { ScaleAnimator { duration: Theme.ms(260); easing.type: Easing.OutBack; easing.overshoot: 2.4 } }
        }
        Rectangle {
            x: 14; y: 9; width: 42; height: 42; radius: 6
            color: Theme.raised
            Text {
                anchors.centerIn: parent
                visible: !face.ready
                text: card.name.slice(0, 1)
                font.family: Theme.font; font.pixelSize: 18; font.bold: true
                color: card.selected ? Theme.ink : Theme.text
            }
            RoundImage { id: face; anchors.fill: parent; source: card.portrait; radius: 6 }
        }
        Text {
            x: 66; y: 16; width: 68; height: 26
            text: card.name
            elide: Text.ElideRight
            verticalAlignment: Text.AlignVCenter
            font.family: Theme.font; font.pixelSize: card.name.length >= 4 ? 13 : 14; font.bold: true
            color: card.selected ? Theme.ink : Theme.text
            Behavior on color { ColorAnimation { duration: Theme.ms(Theme.normal) } }
        }
        Text {
            x: 134; y: 16; width: 24; height: 26
            text: card.tier
            horizontalAlignment: Text.AlignRight; verticalAlignment: Text.AlignVCenter
            font.family: Theme.font; font.pixelSize: 14; font.bold: true
            color: card.selected ? Theme.ink : Theme.muted
            Behavior on color { ColorAnimation { duration: Theme.ms(Theme.normal) } }
        }
    }
    HoverHandler { id: hover }
    Hint { tip: card.tip; text: card.tipText }
}

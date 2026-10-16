import QtQuick
import QtQuick.Effects

// One candidate cell (166×60 in the V2 handoff). Hover, press and selection all animate.
Item {
    id: card
    property int cid
    property string name
    property string title
    property string tier
    property string portrait
    property bool selected
    signal picked(int cid)
    width: 164; height: 60

    Rectangle {
        id: face
        anchors.fill: parent
        radius: 10
        color: card.selected ? Theme.lilac : (hover.hovered ? Theme.hover : Theme.surface)
        scale: tap.pressed ? 0.97 : 1
        Behavior on color { ColorAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
        Behavior on scale { ScaleAnimator { duration: 90; easing.type: Easing.OutCubic } }

        Rectangle {
            x: 4; y: 26; width: 7; height: 7; radius: 3.5
            color: Theme.accent; border.color: Theme.ink; border.width: 1
            scale: card.selected ? 1 : 0
            Behavior on scale { ScaleAnimator { duration: 260; easing.type: Easing.OutBack; easing.overshoot: 2.4 } }
        }

        Rectangle {
            id: portraitFrame
            x: 14; y: 9; width: 42; height: 42; radius: 6
            color: Theme.raised
            Text {
                anchors.centerIn: parent
                visible: portraitImage.status !== Image.Ready
                text: card.name.slice(0, 1)
                font.family: Theme.font; font.pixelSize: 18; font.bold: true
                color: card.selected ? Theme.ink : Theme.text
            }
            Image {
                id: portraitImage
                anchors.fill: parent
                source: card.portrait
                sourceSize: Qt.size(84, 84)
                fillMode: Image.PreserveAspectCrop
                asynchronous: true
                visible: false
            }
            MultiEffect {
                source: portraitImage
                anchors.fill: portraitImage
                maskEnabled: true
                maskSource: portraitMask
                opacity: portraitImage.status === Image.Ready ? 1 : 0
                Behavior on opacity { OpacityAnimator { duration: Theme.normal } }
            }
            Item {
                id: portraitMask
                anchors.fill: parent; visible: false; layer.enabled: true
                Rectangle { anchors.fill: parent; radius: 6 }
            }
        }

        Text {
            x: 66; y: 16; width: 68; height: 26
            text: card.name
            elide: Text.ElideRight
            verticalAlignment: Text.AlignVCenter
            font.family: Theme.font; font.pixelSize: card.name.length >= 4 ? 13 : 14; font.bold: true
            color: card.selected ? Theme.ink : Theme.text
            Behavior on color { ColorAnimation { duration: Theme.normal } }
        }
        Text {
            x: 134; y: 16; width: 24; height: 26
            text: card.tier
            horizontalAlignment: Text.AlignRight; verticalAlignment: Text.AlignVCenter
            font.family: Theme.font; font.pixelSize: 14; font.bold: true
            color: card.selected ? Theme.ink : Theme.muted
            Behavior on color { ColorAnimation { duration: Theme.normal } }
        }
    }

    HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
    TapHandler { id: tap; onTapped: card.picked(card.cid) }
}

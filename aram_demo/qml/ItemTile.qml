import QtQuick

// One core item: a 62px icon over a two-line name, 74px wide.
Item {
    id: tile
    property string name
    property string icon
    property string tipText
    property Item tip: null
    width: 74; height: 102

    Rectangle {
        x: 6; y: 0; width: 62; height: 62; radius: 6
        color: Theme.surface; border.color: Theme.iconBorder
        Icon { anchors.centerIn: parent; visible: !art.ready; name: "question"; color: Theme.muted; width: 24; height: 24 }
        RoundImage { id: art; anchors.fill: parent; anchors.margins: 1; source: tile.icon; radius: 5 }
    }
    Text {
        y: 68; width: 74; height: 34
        text: tile.name
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight
        lineHeight: 17; lineHeightMode: Text.FixedHeight
        font.family: Theme.font; font.pixelSize: 12; color: Theme.text
    }
    Hint { tip: tile.tip; text: tile.tipText }
}

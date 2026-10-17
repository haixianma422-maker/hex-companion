import QtQuick

// Read-only picker with icons and a six-row popup, like the Tk PixelChoice.
// The popup is drawn on `popupLayer` (an item covering the dialog) so it is not clipped by the page.
Item {
    id: choice
    property string value
    property string icon
    property var options: []
    property var optionIcons: []
    property Item popupLayer: null
    signal chosen(string value)
    width: 362; height: 44
    activeFocusOnTab: true

    function takeFocus() { forceActiveFocus() }
    function openList() {
        if (!popupLayer) return
        const origin = choice.mapToItem(popupLayer, 0, 0)
        popup.active = Math.max(0, options.indexOf(value))
        popup.x = origin.x
        popup.y = origin.y + height + popup.height + 4 > popupLayer.height ? origin.y - popup.height - 4 : origin.y + height + 4
        list.positionViewAtIndex(popup.active, ListView.Center)
        popup.visible = true
        popup.forceActiveFocus()
    }

    Rectangle {
        anchors.fill: parent
        radius: 10
        color: Theme.lilac
        border.width: choice.activeFocus || popup.visible ? 2 : 0
        border.color: Theme.accent
        Rectangle {
            x: 6; y: 6; width: 32; height: 32; radius: 6; color: Theme.bg
            RoundImage { anchors.fill: parent; anchors.margins: 3; source: choice.icon; radius: 0; fillMode: Image.PreserveAspectFit }
        }
        Text {
            x: 46; width: parent.width - 80; height: parent.height; verticalAlignment: Text.AlignVCenter
            text: choice.value; elide: Text.ElideRight
            font.family: Theme.font; font.pixelSize: 14; color: Theme.ink
        }
        Icon { x: parent.width - 28; y: 16; width: 14; height: 12; name: "chevron"; color: Theme.ink }
    }
    HoverHandler { cursorShape: Qt.PointingHandCursor }
    TapHandler { onTapped: { choice.forceActiveFocus(); choice.openList() } }
    Keys.onSpacePressed: openList()
    Keys.onReturnPressed: openList()
    Keys.onDownPressed: openList()

    Rectangle {
        id: popup
        parent: choice.popupLayer
        visible: false
        z: 50
        property int active: 0
        width: choice.width; height: Math.min(6, choice.options.length) * 40 + 8
        radius: 10
        color: Theme.surface
        border.color: Theme.line
        onActiveFocusChanged: if (!activeFocus && visible) visible = false
        Keys.onEscapePressed: { visible = false; choice.forceActiveFocus() }
        Keys.onUpPressed: active = Math.max(0, active - 1)
        Keys.onDownPressed: active = Math.min(choice.options.length - 1, active + 1)
        Keys.onReturnPressed: pick(active)
        onActiveChanged: list.positionViewAtIndex(active, ListView.Contain)
        function pick(index) {
            visible = false
            choice.forceActiveFocus()
            choice.chosen(choice.options[index])
        }
        ListView {
            id: list
            anchors.fill: parent; anchors.margins: 4
            clip: true
            model: choice.options
            boundsBehavior: Flickable.StopAtBounds
            delegate: Rectangle {
                width: list.width; height: 40; radius: 8
                color: index === popup.active ? Theme.raised : "transparent"
                Rectangle {
                    x: 6; y: 5; width: 30; height: 30; radius: 6; color: Theme.bg
                    visible: (choice.optionIcons[index] || "") !== ""
                    RoundImage { anchors.fill: parent; anchors.margins: 3; source: choice.optionIcons[index] || ""; radius: 0; fillMode: Image.PreserveAspectFit }
                }
                Text {
                    x: 44; width: parent.width - 52; height: parent.height; verticalAlignment: Text.AlignVCenter
                    text: modelData; elide: Text.ElideRight
                    font.family: Theme.font; font.pixelSize: 14
                    color: modelData === choice.value ? Theme.accent : Theme.text
                }
                HoverHandler { onHoveredChanged: if (hovered) popup.active = index }
                TapHandler { onTapped: popup.pick(index) }
            }
        }
    }
}

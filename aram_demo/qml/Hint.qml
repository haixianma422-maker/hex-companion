import QtQuick

// Attach to any item: shows `text` in the panel's Tip while hovered.
HoverHandler {
    id: handler
    property string text: ""
    property Item tip: null
    readonly property Item area: parent
    onHoveredChanged: report()
    onPointChanged: if (hovered) report()
    function report() {
        if (tip) tip.hover(area, text, hovered, area.mapToItem(tip.parent, point.position.x, point.position.y))
    }
}

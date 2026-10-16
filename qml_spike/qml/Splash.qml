import QtQuick

// Cover-fit splash art with a focal point. A new picture fades in over the old one only
// once it has decoded, so a hero switch never flashes an empty box.
Item {
    id: root
    property string source
    property real focusX: .72
    property real focusY: .42
    property Image front: null

    function show(url, fx, fy) {
        const next = front === a ? b : a
        next.focusX = fx; next.focusY = fy
        if (next.source.toString() === url && next.status === Image.Ready) reveal(next)
        else next.source = url
        if (!url && front) { fadeOut.target = front; fadeOut.restart(); front = null }
    }
    function reveal(next) {
        next.z = 1; if (front) front.z = 0
        fadeIn.stop(); fadeIn.target = next; next.opacity = 0; fadeIn.start()
        front = next
    }
    // Wait for the focal point bindings from the same hero update to settle.
    onSourceChanged: Qt.callLater(root.showCurrent)
    function showCurrent() { show(source, focusX, focusY) }

    NumberAnimation { id: fadeIn; property: "opacity"; to: 1; duration: 280; easing.type: Easing.OutCubic }
    NumberAnimation { id: fadeOut; property: "opacity"; to: 0; duration: 160 }

    component Art: Image {
        property real focusX: .72
        property real focusY: .42
        asynchronous: true
        sourceSize.width: 720
        opacity: 0
        readonly property real cover: implicitWidth > 0 ? Math.max(root.width / implicitWidth, root.height / implicitHeight) : 1
        width: implicitWidth * cover; height: implicitHeight * cover
        x: Math.min(0, Math.max(root.width - width, root.width * .62 - focusX * width))
        y: Math.min(0, Math.max(root.height - height, root.height / 2 - focusY * height))
        onStatusChanged: if (status === Image.Ready && source.toString() === root.source) root.reveal(this)
    }
    Art { id: a }
    Art { id: b }
}

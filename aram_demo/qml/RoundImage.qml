import QtQuick
import QtQuick.Effects

// A cached picture, clipped to rounded corners when radius > 0; it fades in once decoded.
Item {
    id: root
    property url source
    property real radius: 6
    property int fillMode: Image.PreserveAspectCrop
    readonly property bool ready: (radius > 0 ? masked : plain).status === Image.Ready

    Image {
        id: masked
        anchors.fill: parent
        source: root.radius > 0 ? root.source : ""
        fillMode: root.fillMode
        sourceSize: Qt.size(root.width * 2, root.height * 2)
        asynchronous: true
        visible: false
    }
    MultiEffect {
        anchors.fill: parent
        visible: root.radius > 0
        source: masked
        maskEnabled: true
        maskSource: mask
        opacity: masked.status === Image.Ready ? 1 : 0
        Behavior on opacity { OpacityAnimator { duration: Theme.ms(Theme.normal) } }
    }
    Item {
        id: mask
        anchors.fill: parent; visible: false; layer.enabled: true
        Rectangle { anchors.fill: parent; radius: root.radius }
    }
    Image {
        // Transparent artwork such as augment icons needs no mask.
        id: plain
        anchors.fill: parent
        source: root.radius > 0 ? "" : root.source
        fillMode: root.fillMode
        sourceSize: Qt.size(root.width * 2, root.height * 2)
        asynchronous: true
        opacity: status === Image.Ready ? 1 : 0
        Behavior on opacity { OpacityAnimator { duration: Theme.ms(Theme.normal) } }
    }
}

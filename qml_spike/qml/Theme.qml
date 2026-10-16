pragma Singleton
import QtQuick

// V2 tokens copied from aram_demo/ui_drawing.py so the spike compares like for like.
QtObject {
    readonly property color bg: "#191723"
    readonly property color surface: "#282333"
    readonly property color raised: "#393145"
    readonly property color text: "#F7F3EB"
    readonly property color muted: "#B6A6D9"
    readonly property color lilac: "#E9E2F7"
    readonly property color accent: "#DFFF80"
    readonly property color ink: "#191723"
    readonly property color inkMuted: "#55476C"
    readonly property color line: "#443A55"
    readonly property color tierPill: "#D2C0EF"
    readonly property color hover: "#332C40"
    readonly property string font: "Microsoft YaHei UI"

    // Motion tokens: short, decelerating, interruptible.
    readonly property int fast: 120
    readonly property int normal: 200
    readonly property int slow: 260
}

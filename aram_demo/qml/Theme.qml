pragma Singleton
import QtQuick

// V2 tokens (aram_demo/ui_drawing.py before the Qt move). A redesign changes this file first.
QtObject {
    readonly property color bg: "#191723"
    readonly property color surface: "#282333"
    readonly property color raised: "#393145"
    readonly property color hover: "#332C40"
    readonly property color text: "#F7F3EB"
    readonly property color muted: "#B6A6D9"
    readonly property color lilac: "#E9E2F7"
    readonly property color accent: "#DFFF80"
    readonly property color accentHover: "#EAFFAD"
    readonly property color ink: "#191723"
    readonly property color inkMuted: "#55476C"
    readonly property color line: "#443A55"
    readonly property color tierPill: "#D2C0EF"
    readonly property color iconBorder: "#645775"
    readonly property color scrollThumb: "#665974"
    readonly property color error: "#FFB7BE"
    readonly property color footer: "#211C2D"
    readonly property string font: "Microsoft YaHei UI"
    readonly property var gradeColors: ({ "S": "#DFFF80", "A": "#E9E2F7", "B": "#D6C8ED", "C": "#C4B3DD",
                                          "D": "#B3A3C9", "E": "#A796BA", "—": "#B3A3C9" })

    // Off when the settings switch or the Windows animation preference says so. "Off" is 1 ms,
    // not 0: a zero-length Animator never writes its end value back, which left items invisible.
    property bool motion: true
    function ms(duration) { return motion ? duration : 1 }

    readonly property int fast: 120
    readonly property int normal: 200
    readonly property int slow: 260
}

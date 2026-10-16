import QtQuick
import QtQuick.Shapes

// Stroke icons on a 24-unit grid, matching the Tk drawing helpers in ui_drawing.icon().
Shape {
    id: icon
    property string name: "minus"
    property color color: Theme.text
    property real stroke: 1.6
    width: 16; height: 16
    preferredRendererType: Shape.CurveRenderer

    function poly(points) {
        let d = "M" + points[0][0] + " " + points[0][1]
        for (let i = 1; i < points.length; ++i) d += " L" + points[i][0] + " " + points[i][1]
        return d
    }
    function ring(count, radius, closed) {
        const out = []
        for (let i = 0; i <= count; ++i) {
            const a = i * 2 * Math.PI / count
            out.push([12 + radius(i) * Math.cos(a), 12 + radius(i) * Math.sin(a)])
        }
        return out
    }
    readonly property string path: {
        if (name === "minus") return "M2 12 L22 12"
        if (name === "refresh") {
            const pts = []
            for (let i = 0; i <= 28; ++i) {
                const a = (15 + i * 300 / 28) * Math.PI / 180
                pts.push([12 + 8.6 * Math.cos(a), 12 + 8.6 * Math.sin(a)])
            }
            return poly(pts) + " M13.9 1 L18.7 4.6 L13.9 7"
        }
        if (name === "settings")
            return poly(ring(64, i => (i % 8 >= 2 && i % 8 <= 5) ? 9.4 : 11.8)) +
                   " M15.8 12 A3.8 3.8 0 1 1 8.2 12 A3.8 3.8 0 1 1 15.8 12"
        return ""
    }

    ShapePath {
        strokeColor: icon.color
        strokeWidth: icon.stroke * 24 / icon.width
        fillColor: "transparent"
        capStyle: ShapePath.RoundCap
        joinStyle: ShapePath.RoundJoin
        scale: Qt.size(icon.width / 24, icon.height / 24)
        PathSvg { path: icon.path }
    }
}

import QtQuick
import QtQuick.Shapes

// Stroke icons on a 24-unit grid, traced from the Tk drawing helper ui_drawing.icon().
Shape {
    id: icon
    property string name: "minus"
    property color color: Theme.text
    property real stroke: 1.6
    width: 16; height: 16
    preferredRendererType: Shape.CurveRenderer

    function poly(points, closed) {
        let d = "M" + points[0][0] * 24 + " " + points[0][1] * 24
        for (let i = 1; i < points.length; ++i) d += " L" + points[i][0] * 24 + " " + points[i][1] * 24
        return closed ? d + " Z" : d
    }
    function circle(cx, cy, r) {
        return "M" + (cx + r) * 24 + " " + cy * 24 + " A" + r * 24 + " " + r * 24 + " 0 1 1 " + (cx - r) * 24 + " " + cy * 24
             + " A" + r * 24 + " " + r * 24 + " 0 1 1 " + (cx + r) * 24 + " " + cy * 24
    }
    readonly property string path: {
        switch (name) {
        case "minus": return poly([[.08, .5], [.92, .5]])
        case "close": return poly([[.12, .12], [.88, .88]]) + " " + poly([[.88, .12], [.12, .88]])
        case "chevron": return poly([[.12, .3], [.5, .7], [.88, .3]])
        case "scan": return poly([[.35, .08], [.08, .08], [.08, .35]]) + " " + poly([[.65, .08], [.92, .08], [.92, .35]])
                          + " " + poly([[.08, .65], [.08, .92], [.35, .92]]) + " " + poly([[.65, .92], [.92, .92], [.92, .65]])
        case "refresh": {
            const pts = []
            for (let i = 0; i <= 28; ++i) {
                const a = (15 + i * 300 / 28) * Math.PI / 180
                pts.push([.5 + .36 * Math.cos(a), .5 + .36 * Math.sin(a)])
            }
            return poly(pts) + " " + poly([[.58, .04], [.78, .19], [.58, .29]])
        }
        case "settings": {
            const pts = []
            for (let i = 0; i <= 64; ++i) {
                const a = i * 2 * Math.PI / 64, r = (i % 8 >= 2 && i % 8 <= 5) ? .39 : .49
                pts.push([.5 + r * Math.cos(a), .5 + r * Math.sin(a)])
            }
            return poly(pts, true) + " " + circle(.5, .5, .16)
        }
        case "info": return circle(.5, .5, .44) + " " + poly([[.5, .45], [.5, .72]])
        case "question": return circle(.5, .5, .44)
                              + " " + poly([[.33, .34], [.4, .25], [.57, .25], [.67, .34], [.65, .45], [.5, .54], [.5, .61]])
        case "folder": return poly([[.06, .3], [.06, .85], [.94, .85], [.94, .26], [.48, .26], [.38, .12], [.06, .12]], true)
        }
        return ""
    }
    // Filled parts: the star, and the dots of info/question.
    readonly property string fill: {
        switch (name) {
        case "star": return poly([[.5, 0], [.62, .36], [1, .5], [.62, .64], [.5, 1], [.38, .64], [0, .5], [.38, .36]], true)
        case "info": return circle(.5, .3, .04)
        case "question": return circle(.5, .77, .04)
        }
        return ""
    }

    ShapePath {
        strokeColor: icon.path ? icon.color : "transparent"
        strokeWidth: icon.stroke * 24 / Math.max(1, icon.width)
        fillColor: "transparent"
        capStyle: ShapePath.RoundCap
        joinStyle: ShapePath.RoundJoin
        scale: Qt.size(icon.width / 24, icon.height / 24)
        PathSvg { path: icon.path }
    }
    ShapePath {
        strokeColor: "transparent"
        fillColor: icon.fill ? icon.color : "transparent"
        scale: Qt.size(icon.width / 24, icon.height / 24)
        PathSvg { path: icon.fill }
    }
}

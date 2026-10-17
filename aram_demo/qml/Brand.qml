import QtQuick
import QtQuick.Shapes

// Same path as aram_demo/ui_drawing._BRAND; the inner mark is punched out with odd-even fill.
Shape {
    id: brand
    property color color: Theme.accent
    width: 20; height: 20
    preferredRendererType: Shape.CurveRenderer
    ShapePath {
        fillColor: brand.color
        strokeColor: "transparent"
        fillRule: ShapePath.OddEvenFill
        scale: Qt.size(brand.width / 24, brand.height / 24)
        PathSvg {
            path: "M12 1 C14 1 14 6 15.5 7 L21 7 C24 7 22 10 19 12 L21 18 C22 21 18 21 15 18 L12 23 C10 25 8 21 8 17 L2 17 C-1 17 1 13 5 11 L2 7 C0 4 4 3 8 6 L10 2 C10.5 1 11 1 12 1 Z M7 9 L10 12 L7 15 L10 15 L13 12 L10 9 Z"
        }
    }
}

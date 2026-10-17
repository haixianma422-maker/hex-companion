import QtQuick

// 44×26 switch; Space or Enter toggles it from the keyboard.
Rectangle {
    id: toggle
    property bool checked
    signal toggled(bool value)
    width: 44; height: 26; radius: 13
    color: checked ? Theme.accent : Theme.raised
    border.color: activeFocus ? Theme.accent : "transparent"
    activeFocusOnTab: true
    Behavior on color { ColorAnimation { duration: Theme.ms(Theme.fast) } }

    Rectangle {
        y: 4; width: 18; height: 18; radius: 9
        x: toggle.checked ? 22 : 4
        color: Theme.text
        Behavior on x { XAnimator { duration: Theme.ms(180); easing.type: Easing.OutCubic } }
    }
    HoverHandler { cursorShape: Qt.PointingHandCursor }
    TapHandler { onTapped: { toggle.forceActiveFocus(); toggle.toggled(!toggle.checked) } }
    Keys.onSpacePressed: toggled(!checked)
    Keys.onReturnPressed: toggled(!checked)
}

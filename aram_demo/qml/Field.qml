import QtQuick

// Rounded single-line field. With `capture`, it records a key combination instead of text:
// F1–F12 alone, or Ctrl/Alt/Shift with a letter or digit (the rules in aram_demo/hotkeys.py).
Rectangle {
    id: field
    property string text
    property string fieldId
    property string error
    property bool capture: false
    property bool center: false
    property int fontSize: 14
    property int inset: 12
    property color fill: Theme.lilac
    property color ink: fill === Theme.lilac ? Theme.ink : Theme.text
    signal edited(string value)
    radius: 10
    color: fill
    border.width: error || input.activeFocus ? 2 : 0
    border.color: error ? Theme.error : Theme.accent

    function takeFocus() { input.forceActiveFocus() }

    TextInput {
        id: input
        anchors.fill: parent
        anchors.leftMargin: field.inset; anchors.rightMargin: field.inset
        verticalAlignment: TextInput.AlignVCenter
        horizontalAlignment: field.center ? TextInput.AlignHCenter : TextInput.AlignLeft
        clip: true
        text: field.text
        readOnly: field.capture
        selectByMouse: !field.capture
        font.family: Theme.font; font.pixelSize: field.fontSize
        color: field.ink
        selectionColor: Theme.raised
        onTextEdited: field.edited(text)
        Keys.onPressed: event => {
            if (!field.capture || event.key === Qt.Key_Tab || event.key === Qt.Key_Backtab) return
            const named = event.key >= Qt.Key_F1 && event.key <= Qt.Key_F12
            const letter = event.text.length === 1 && /[A-Za-z0-9]/.test(event.text) ? event.text.toUpperCase()
                         : (event.key >= Qt.Key_A && event.key <= Qt.Key_Z) ? String.fromCharCode(event.key)
                         : (event.key >= Qt.Key_0 && event.key <= Qt.Key_9) ? String.fromCharCode(event.key) : ""
            const modifiers = []
            if (event.modifiers & Qt.ControlModifier) modifiers.push("Ctrl")
            if (event.modifiers & Qt.AltModifier) modifiers.push("Alt")
            if (event.modifiers & Qt.ShiftModifier) modifiers.push("Shift")
            if (named) field.edited(modifiers.concat(["F" + (event.key - Qt.Key_F1 + 1)]).join("+"))
            else if (letter && modifiers.length) field.edited(modifiers.concat([letter]).join("+"))
            event.accepted = true
        }
    }
    HoverHandler { cursorShape: field.capture ? Qt.PointingHandCursor : Qt.IBeamCursor }
}

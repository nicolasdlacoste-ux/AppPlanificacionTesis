try {
    var fso = new ActiveXObject("Scripting.FileSystemObject");
    var file = fso.OpenTextFile("webapp/app.js", 1);
    var content = file.ReadAll();
    file.Close();
    eval("function test() { " + content + " }");
    WScript.Echo("Syntax OK");
} catch(e) {
    WScript.Echo("Error: " + e.message + " at line " + (e.line || "unknown"));
}

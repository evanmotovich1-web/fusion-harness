import Foundation
import PDFKit

let args = CommandLine.arguments
if args.count != 3 { fputs("usage: extract input output\n", stderr); exit(2) }
let input = URL(fileURLWithPath: args[1])
let output = URL(fileURLWithPath: args[2])
guard let doc = PDFDocument(url: input) else { fputs("open failed\n", stderr); exit(3) }
var all = "PAGES\t\(doc.pageCount)\n"
for i in 0..<doc.pageCount {
    let text = doc.page(at: i)?.string ?? ""
    all += "\n----- PDF PAGE \(i + 1) -----\n" + text + "\n"
}
try all.write(to: output, atomically: true, encoding: .utf8)
print("pages=\(doc.pageCount) chars=\(all.count)")

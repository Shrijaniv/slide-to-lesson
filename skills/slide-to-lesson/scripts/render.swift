import AppKit
import PDFKit
import Foundation

guard CommandLine.arguments.count == 3 else { fputs("Usage: render.swift input.pdf output-directory\n", stderr); exit(2) }
let url = URL(fileURLWithPath: CommandLine.arguments[1])
let output = URL(fileURLWithPath: CommandLine.arguments[2], isDirectory: true)
guard let document = PDFDocument(url: url), document.pageCount > 0 else { fputs("Could not open PDF\n", stderr); exit(1) }
guard document.pageCount <= 100 else { fputs("The PDF must have 100 pages or fewer\n", stderr); exit(1) }
var pages: [[String: String]] = []
for index in 0..<document.pageCount {
    guard let page = document.page(at: index) else { continue }
    let bounds = page.bounds(for: .mediaBox)
    let scale = min(1600.0 / max(bounds.width, 1), 1200.0 / max(bounds.height, 1))
    let size = NSSize(width: max(1, bounds.width * scale), height: max(1, bounds.height * scale))
    let image = page.thumbnail(of: size, for: .mediaBox)
    guard let tiff = image.tiffRepresentation,
          let bitmap = NSBitmapImageRep(data: tiff),
          let jpeg = bitmap.representation(using: .jpeg, properties: [.compressionFactor: 0.82]) else {
        fputs("Could not render page \(index + 1)\n", stderr); exit(1)
    }
    let name = String(format: "slide-%03d.jpg", index + 1)
    try jpeg.write(to: output.appendingPathComponent(name))
    pages.append(["image": name, "text": page.string ?? ""])
}
let data = try JSONSerialization.data(withJSONObject: pages, options: [])
try data.write(to: output.appendingPathComponent("pages.json"))

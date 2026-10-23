extends RefCounted
## Small vector service icons use the HUD's gold and teal palette.
static func texture(storage: bool) -> Texture2D:
	var path := '<path d="M5 14h22v14H5z M4 14l4-9h16l4 9 M5 20h22 M14 18h4v6h-4z"/>' if storage else '<path d="M16 4v24 M9 28h14 M4 10h24 M6 10L2 20h8L6 10 M26 10l-4 10h8l-4-10 M2 20q4 6 8 0 M22 20q4 6 8 0"/>'
	var svg := '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32"><g fill="none" stroke="#e5be78" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round">' + path + '</g></svg>'
	var bitmap := Image.new()
	bitmap.load_svg_from_string(svg, 2.0)
	return ImageTexture.create_from_image(bitmap)

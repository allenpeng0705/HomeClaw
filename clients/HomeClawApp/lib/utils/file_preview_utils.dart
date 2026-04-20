library file_preview_utils;

/// Shared file-type detection helpers for file preview widgets.
const _textPreviewExtensions = {
  '.txt', '.md', '.csv', '.json', '.log', '.yml', '.yaml', '.xml',
  '.dart', '.py', '.ts', '.tsx', '.js', '.jsx', '.css', '.html', '.htm',
  '.rs', '.go', '.java', '.kt', '.swift', '.c', '.h', '.cpp', '.sh',
  '.toml', '.gradle', '.properties',
};

const _imageExtensions = {'.png', '.jpg', '.jpeg', '.gif', '.webp'};

/// Whether [name] (filename) is a displayable image that can be previewed inline.
bool isDisplayableImageName(String name) {
  final n = name.toLowerCase();
  return _imageExtensions.any((e) => n.endsWith(e));
}

/// Whether [name] is a text file whose contents can be previewed inline.
bool isTextPreviewName(String name) {
  final n = name.toLowerCase();
  return _textPreviewExtensions.any((e) => n.endsWith(e));
}

/// Whether [name] is a Markdown file.
bool isMarkdownName(String name) {
  final n = name.toLowerCase();
  return n.endsWith('.md') || n.endsWith('.markdown');
}

/// Whether [name] is a PDF file.
bool isPdfName(String name) {
  return name.toLowerCase().endsWith('.pdf');
}

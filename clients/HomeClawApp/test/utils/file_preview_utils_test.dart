import 'package:flutter_test/flutter_test.dart';
import 'package:home_claw_app/utils/file_preview_utils.dart';

void main() {
  group('isDisplayableImageName', () {
    test('returns true for common image extensions', () {
      expect(isDisplayableImageName('photo.png'), true);
      expect(isDisplayableImageName('PHOTO.PNG'), true);
      expect(isDisplayableImageName('image.jpg'), true);
      expect(isDisplayableImageName('image.jpeg'), true);
      expect(isDisplayableImageName('animation.gif'), true);
      expect(isDisplayableImageName('photo.webp'), true);
    });

    test('returns false for non-image files', () {
      expect(isDisplayableImageName('document.pdf'), false);
      expect(isDisplayableImageName('script.py'), false);
      expect(isDisplayableImageName('data.json'), false);
    });

    test('returns false for files without extensions', () {
      expect(isDisplayableImageName('README'), false);
      expect(isDisplayableImageName('Makefile'), false);
    });
  });

  group('isTextPreviewName', () {
    test('returns true for text file extensions', () {
      expect(isTextPreviewName('readme.md'), true);
      expect(isTextPreviewName('config.yml'), true);
      expect(isTextPreviewName('data.yaml'), true);
      expect(isTextPreviewName('log.txt'), true);
      expect(isTextPreviewName('data.json'), true);
      expect(isTextPreviewName('main.dart'), true);
      expect(isTextPreviewName('app.py'), true);
      expect(isTextPreviewName('index.html'), true);
      expect(isTextPreviewName('style.css'), true);
      expect(isTextPreviewName('Cargo.toml'), true);
      expect(isTextPreviewName('build.gradle'), true);
      expect(isTextPreviewName('app.properties'), true);
    });

    test('returns false for binary files', () {
      expect(isTextPreviewName('photo.png'), false);
      expect(isTextPreviewName('video.mp4'), false);
      expect(isTextPreviewName('archive.zip'), false);
      expect(isTextPreviewName('binary.exe'), false);
    });
  });

  group('isMarkdownName', () {
    test('returns true for markdown files', () {
      expect(isMarkdownName('README.md'), true);
      expect(isMarkdownName('notes.MD'), true);
      expect(isMarkdownName('changelog.markdown'), true);
      expect(isMarkdownName('DOC.MARKDOWN'), true);
    });

    test('returns false for non-markdown files', () {
      expect(isMarkdownName('readme.txt'), false);
      expect(isMarkdownName('doc.pdf'), false);
      expect(isMarkdownName('notes'), false);
    });
  });

  group('isPdfName', () {
    test('returns true for pdf files', () {
      expect(isPdfName('document.pdf'), true);
      expect(isPdfName('DOC.PDF'), true);
      expect(isPdfName('paper.Pdf'), true);
    });

    test('returns false for non-pdf files', () {
      expect(isPdfName('document.txt'), false);
      expect(isPdfName('document.docx'), false);
      expect(isPdfName('data'), false);
    });
  });
}

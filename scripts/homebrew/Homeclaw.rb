# Homebrew Formula for HomeClaw Core (CLI).
# Install: brew tap <your-org>/homeclaw && brew install homeclaw
# Run: homeclaw start
#
# To use this formula:
# 1. Create a tap repo (e.g. github.com/your-org/homebrew-homeclaw).
# 2. Copy this file to Formula/homeclaw.rb in that repo.
# 3. Replace HOMECLAW_REPO and version/url with your GitHub repo and release tarball.
# 4. On release: upload a source tarball (e.g. from GitHub "Source code (tar.gz)") and set the URL below.

class Homeclaw < Formula
  desc "HomeClaw Core — local AI assistant server and API"
  homepage "https://github.com/your-org/HomeClaw"
  # Use a release tarball so the formula has a fixed version and checksum.
  # Example: https://github.com/your-org/HomeClaw/archive/refs/tags/v1.0.0.tar.gz
  url "https://github.com/your-org/HomeClaw/archive/refs/tags/v1.0.0.tar.gz"
  sha256 "REPLACE_WITH_SHA256_OF_TARBALL"  # brew fetch homeclaw then brew audit --fix
  license "MIT"
  version "1.0.0"

  depends_on "python@3.11"

  def install
    # HomeClaw expects to be run from a directory containing main.py, base/, core/, config/, etc.
    # Copy the project into the Cellar and install there; the wrapper script will set cwd.
    pkgshare.install "main.py"
    pkgshare.install "base", "core", "llm", "memory", "tools", "hybrid_router",
                     "plugins", "channels", "system_plugins", "examples", "ui"
    pkgshare.install "config" if Dir.exist?("config")
    pkgshare.install "requirements.txt"

    venv = virtualenv_create(libexec, "python3.11")
    venv.pip_install "-r", (pkgshare/"requirements.txt")
    (bin/"homeclaw").write <<~EOS
      #!/bin/bash
      cd "#{pkgshare}" && exec "#{libexec}/bin/python" -m main "$@"
    EOS
    (bin/"homeclaw").chmod 0755
  end

  def caveats
    <<~EOS
      HomeClaw Core is installed. Run:
        homeclaw start

      Config is in: #{pkgshare}/config/
      Put GGUF models in ~/HomeClaw/models (or set model_path in config).

      Companion app (Mac/Windows) is separate: download from GitHub Releases or build from clients/HomeClawApp.
    EOS
  end

  test do
    # Basic check that the module loads
    system "#{bin}/homeclaw", "--help"
  end
end

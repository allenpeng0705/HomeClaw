# Homebrew Formula for HomeClaw Core (Mac and Linux).
# Install: brew tap allenpeng0705/homeclaw && brew install homeclaw
# Run: homeclaw start   or   homeclaw portal
#
# The canonical copy for the tap repo is in scripts/homebrew-tap/Formula/homeclaw.rb.
# Copy that file to your tap repo (github.com/allenpeng0705/homebrew-homeclaw).
# On each release: update url, version, and sha256 (run scripts/homebrew/get-sha256.sh <version>).

class Homeclaw < Formula
  desc "HomeClaw Core — local AI assistant server and API"
  homepage "https://github.com/allenpeng0705/HomeClaw"
  url "https://github.com/allenpeng0705/HomeClaw/archive/refs/tags/v1.0.0.tar.gz"
  sha256 "REPLACE_WITH_SHA256"
  license "MIT"
  version "1.0.0"

  depends_on "python@3.11"

  def install
    pkgshare.install "main.py"
    pkgshare.install "requirements.txt"
    pkgshare.install "base", "core", "llm", "memory", "tools", "hybrid_router",
                     "plugins", "channels", "system_plugins", "portal", "ui",
                     "skills"
    pkgshare.install "config" if Dir.exist?("config")
    pkgshare.install "external_plugins" if Dir.exist?("external_plugins")
    pkgshare.install "examples" if Dir.exist?("examples")

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
      HomeClaw Core is installed. Commands:
        homeclaw start    # start Core
        homeclaw portal   # start Portal at http://127.0.0.1:18472
        homeclaw doctor   # check environment

      Config: #{pkgshare}/config/
      Put GGUF models in ~/HomeClaw/models (or set model_path in config).

      Companion app: download from GitHub Releases or build from clients/HomeClawApp.
    EOS
  end

  test do
    system "#{bin}/homeclaw", "--help"
  end
end

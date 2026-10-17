"""Sign and notarize an already prepared macOS bundle using the local keychain.

Run on a Mac. Apple credentials stay in a preconfigured notarytool keychain
profile; never pass private keys/passwords through this script or Git.
"""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

import macos_package


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--identity", required=True, help="installed Developer ID Application certificate common name")
    parser.add_argument("--notary-profile", required=True, help="existing notarytool keychain profile name")
    options = parser.parse_args()
    macos_package.native()
    app = options.app.resolve(strict=True)
    if app.name != "Rabbit Lands.app" or not options.identity.startswith("Developer ID Application:"):
        parser.error("Select the complete Rabbit Lands.app and its Developer ID Application identity.")
    macos_package.sign(app, options.identity)
    with tempfile.TemporaryDirectory(prefix="rabbitlands-notary-") as temp:
        archive = Path(temp) / "RabbitLands.zip"
        subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(app), str(archive)], check=True)
        result = subprocess.run(["xcrun", "notarytool", "submit", str(archive), "--keychain-profile",
                                 options.notary_profile, "--wait", "--output-format", "json"],
                                check=True, capture_output=True, text=True)
        if json.loads(result.stdout).get("status") != "Accepted":
            raise SystemExit("Apple has not accepted this bundle. Inspect the notarization log before distribution.")
    subprocess.run(["xcrun", "stapler", "staple", str(app)], check=True)
    subprocess.run(["xcrun", "stapler", "validate", str(app)], check=True)
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True)
    subprocess.run(["spctl", "--assess", "--type", "execute", "--verbose", str(app)], check=True)
    print("Developer ID signature, accepted notarization, stapled ticket and Gatekeeper assessment passed.")


if __name__ == "__main__":
    main()

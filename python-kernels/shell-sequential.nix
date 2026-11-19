# Sequential-only MVP environment. Keep the current compiler source and package
# pin, but avoid the OpenCilk/LLVM toolchain required by the repository shell.
let
  pkgs = import (builtins.fetchTarball {
    url = "https://github.com/NixOS/nixpkgs/archive/refs/tags/25.11.tar.gz";
    sha256 = "1zn1lsafn62sz6azx6j735fh4vwwghj8cc9x91g5sx2nrg23ap9k";
  }) {};
  root = ../.;
in pkgs.mkShell {
  inputsFrom = [
    (pkgs.haskellPackages.callCabal2nix "gibbon-compiler" (root + "/gibbon-compiler") {}).env
  ];
  packages = with pkgs; [ cabal-install gcc boehmgc uthash rustc cargo pkg-config ];
  shellHook = ''
    export GIBBONDIR=${builtins.toString root}
    export CC=gcc
  '';
}

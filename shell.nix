let
  pkgs = import (builtins.fetchGit {
                   url = "https://github.com/nixos/nixpkgs/";
                   ref = "refs/tags/25.05";
                 }) {};

  clang = pkgs.clang_16;
  llvm = pkgs.llvm_16;
  gibbon_dir = builtins.toString ./.;
in
  with pkgs;

  # we are stuck with GCC 7 because Cilk was kicked out in GCC 8,
  # OpenCilk needs packaging in nixpkgs, see
  # https://github.com/NixOS/nixpkgs/issues/144256
  mkShell.override { }  {

    # we use default Haskell toolchain supplied with the chosen nixpkgs; this way we hit their cache
    inputsFrom = [ (pkgs.haskellPackages.callCabal2nix "gibbon-compiler" ./gibbon-compiler { }).env ];

    name = "basicGibbonEnv";
    buildInputs = [
                    # C/C++
                    clang llvm boehmgc uthash
                    # Rust
                    rustc cargo
                    # Racket
                    racket
                    # Other utilities
                    stdenv ncurses unzip which rr rustfmt clippy ghcid gdb valgrind
                  ];
    shellHook = ''
      export GIBBONDIR=${gibbon_dir}
      source set_env.sh
      export PATH=$PWD/opencilk/bin/:$PATH
      export CC=clang
      export CXX=clang++
      
      export CPATH=${pkgs.uthash}/include:$CPATH
    '';
  }

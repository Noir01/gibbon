{ pkgs ? import <nixpkgs> {} }:

let
  gcc14Stdenv = pkgs.overrideCC pkgs.stdenv pkgs.gcc14;
  inherit (pkgs) fetchgit cmake ninja git;

  infrastructureSrc = fetchgit {
    url    = "https://github.com/OpenCilk/infrastructure.git";
    rev    = "opencilk/v3.0";
    sha256 = "dpBiCPT0ZwKLi1ezD06/hVG40QW9azunqXPxwn0gDO4=";
  };
  opencilkProjectSrc = fetchgit {
    url    = "https://github.com/OpenCilk/opencilk-project.git";
    rev    = "opencilk/v3.0";
    sha256 = "QIBpCsdDVbXh35VGVDymI9CvAnTo1SA0UxZvJ0LUy0k=";
  };
  cheetahSrc = fetchgit {
    url    = "https://github.com/OpenCilk/cheetah.git";
    rev    = "opencilk/v3.0";
    sha256 = "qBjYuCqw7Dk3IFrf9nEkGMjdveev2WiX9zSDHoSpnDc=";
  };
  productivityToolsSrc = fetchgit {
    url    = "https://github.com/OpenCilk/productivity-tools.git";
    rev    = "opencilk/v3.0";
    sha256 = "E59xva3+TFo7VCUO7/qVgHr0ZSiZq1cByRzCVfrQlP8=";
  };

  combinedSrc = pkgs.runCommand "combine-all-repos" { } ''
    mkdir -p $out/infrastructure/opencilk
    cp -r ${opencilkProjectSrc}/* $out/infrastructure/opencilk/

    mkdir -p $out/infrastructure/opencilk/cheetah
    cp -r ${cheetahSrc}/* $out/infrastructure/opencilk/cheetah/

    mkdir -p $out/infrastructure/opencilk/cilktools
    cp -r ${productivityToolsSrc}/* $out/infrastructure/opencilk/cilktools/
  '';

  # build Clang (unwrapped)
  clangUnwrapped = gcc14Stdenv.mkDerivation {
    pname   = "opencilk-clang-unwrapped";
    version = "v3.0";
    src     = combinedSrc;

    nativeBuildInputs = [
      pkgs.git
      
      pkgs.zlib
      pkgs.libxml2
      pkgs.libffi
      pkgs.libpfm
      pkgs.libxcrypt

      pkgs.jemalloc
      pkgs.libunwind

      pkgs.cmake
      
      pkgs.python3
      pkgs.python3Packages.pygments
      pkgs.python3Packages.pyyaml
      
      pkgs.ncurses
      pkgs.libedit

      pkgs.llvmPackages.clang
      pkgs.llvmPackages_16.bintools

      pkgs.valgrind

      pkgs.ninja

      pkgs.binutils
    ];

    phases = [ "unpackPhase" "buildPhase" "installPhase" ];

    buildPhase = ''
      mkdir build && cd build
      cmake -G Ninja \
        -DLLVM_ENABLE_PROJECTS="clang;clang-tools-extra" \
        -DLLVM_TARGETS_TO_BUILD=host \
        -DC_INCLUDE_DIRS=${pkgs.glibc.dev}/include \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=$out \
        $src/infrastructure/opencilk/llvm
      cmake --build . --target clang -- -j 5
    '';

    installPhase = "ninja install-clang";
  };

  # Wrap the compiler so it is hopefully Nix‑aware (cc‑wrapper)
  clangWrapped = pkgs.wrapCCWith rec {
    cc = clangUnwrapped;
    bintools = pkgs.wrapBintoolsWith {
      bintools = pkgs.binutils;
      libc     = pkgs.glibc;
    };
    extraPackages = [ pkgs.gcc14.cc ];
  };

  clangStdenv = pkgs.overrideCC pkgs.stdenv clangWrapped;

  # build the rest of OpenCilk
  myOpenCilk = clangStdenv.mkDerivation rec {
    pname   = "openCilk";
    version = "v3.0";
    src     = combinedSrc;

    nativeBuildInputs = [
      pkgs.git
      
      pkgs.zlib
      pkgs.libxml2
      pkgs.libffi
      pkgs.libpfm
      pkgs.libxcrypt

      pkgs.jemalloc
      pkgs.libunwind

      pkgs.cmake
      
      pkgs.python3
      pkgs.python3Packages.pygments
      pkgs.python3Packages.pyyaml
      
      pkgs.ncurses
      pkgs.libedit

      pkgs.llvmPackages.clang
      pkgs.llvmPackages_16.bintools

      pkgs.valgrind

      pkgs.ninja

      pkgs.binutils

      clangWrapped
    ];

    phases = [ "unpackPhase" "buildPhase" "installPhase" ];

    buildPhase = ''
      mkdir build && cd build
      cmake -G Ninja \
        -DCMAKE_C_COMPILER=clang   \
        -DCMAKE_CXX_COMPILER=clang++ \
        -DCLANG_CONFIG_FILE_SYSTEM_DIR=$out/etc/clang \
        -DLLVM_ENABLE_PROJECTS="clang;clang-tools-extra" \
        -DLLVM_ENABLE_RUNTIMES="cheetah;cilktools" \
        -DLLVM_TARGETS_TO_BUILD=host \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=$out \
        $src/infrastructure/opencilk/llvm
      cmake --build . -- -j
    '';
    installPhase = "ninja install";
  };

in
{
  inherit myOpenCilk clangWrapped;
}


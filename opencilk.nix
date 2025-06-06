{ pkgs ? import <nixpkgs> {} }:

let
  gcc14Stdenv = pkgs.overrideCC pkgs.stdenv pkgs.gcc14;

  inherit (pkgs) fetchgit;

  infrastructureSrc = fetchgit {
    url    = "https://github.com/OpenCilk/infrastructure.git";
    rev    = "opencilk/v2.1";
    sha256 = "01o3apUzIwFubvgJu+aonp7Ly7AMDvZKkOV7sz0pXBU=";
  };

  opencilkProjectSrc = fetchgit {
    url    = "https://github.com/OpenCilk/opencilk-project.git";
    rev    = "opencilk/v2.1";
    sha256 = "Z4CjQU4wC0ubQSWaieDoMycxmhpPqnSEevMWQdRNUYY=";
  };

  cheetahSrc = fetchgit {
    url    = "https://github.com/OpenCilk/cheetah.git";
    rev    = "opencilk/v2.1";
    sha256 = "QUlH2mKftfJe4xjmGc3Cumgi8aqrtGVxDTmfXRX/cB4=";
  };

  productivityToolsSrc = fetchgit {
    url    = "https://github.com/OpenCilk/productivity-tools.git";
    rev    = "opencilk/v2.1";
    sha256 = "6+pUxNwkYUfORjeDzX5MJXzYwJbTodF019hVkDow+uQ=";
  };

  combinedSrc = pkgs.runCommand "combine-all-repos" { } ''
    mkdir -p $out

    mkdir -p $out/infrastructure
    cp -r ${infrastructureSrc}/*  $out/infrastructure/

    mkdir -p $out/infrastructure/opencilk
    cp -r ${opencilkProjectSrc}/* $out/infrastructure/opencilk/

    mkdir -p $out/infrastructure/opencilk/cheetah
    cp -r ${cheetahSrc}/*        $out/infrastructure/opencilk/cheetah/

    mkdir -p $out/infrastructure/opencilk/cilktools
    cp -r ${productivityToolsSrc}/* $out/infrastructure/opencilk/cilktools/

    mkdir -p $out/infrastructure/build

  '';

  myOpenCilk = gcc14Stdenv.mkDerivation rec {
    pname    = "openCilk-from-source";
    version  = "2.1";

    # The top‐level src is “combinedSrc” (which contains infrastructure/ and its subfolders)
    src = combinedSrc;

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

      # pkgs.ocaml
      # pkgs.ocamlPackages.findlib
      # pkgs.ocamlPackages.ctypes

      pkgs.valgrind

      pkgs.ninja

      pkgs.binutils
    ];

    phases = [ "unpackPhase" "buildPhase" "installPhase" ];

    buildPhase = ''
      set -ex

      mkdir -p $PWD/build
      BUILD_DIR=$PWD/build

      export OPENCILK_INSTALL_PREFIX=$out

      INFRA_DIR="$src/infrastructure"

      OPENCILK_DIR="$src/infrastructure/opencilk"

      sh $INFRA_DIR/tools/build $OPENCILK_DIR $BUILD_DIR
    '';

    installPhase = ''
      set -ex
      cd $BUILD_DIR
      cmake --install . --prefix $OPENCILK_INSTALL_PREFIX
    '';
  };
in

{ inherit myOpenCilk; }


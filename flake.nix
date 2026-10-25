{
  description = "FEM of OpenSCAD models driven by //@sim comments";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = import nixpkgs { inherit system; };

        # what scadfem runs
        runtime = with pkgs; [
          python3
          gmsh
          calculix-ccx
          openscad
        ];

        bashball = pkgs.stdenvNoCC.mkDerivation {
          pname = "bashball";
          version = "1.6.4";
          src = pkgs.fetchurl {
            url = "https://github.com/blkgoose/bashball/releases/download/v1.6.4/bashball";
            sha256 = "0lf0bzxk3ibhg4y1acf43akzykyg2p70sxykw4ckap633wmfgf1y";
          };
          dontUnpack = true;
          nativeBuildInputs = [ pkgs.makeWrapper ];
          installPhase = ''
            install -Dm755 $src $out/libexec/bashball
            makeWrapper $out/libexec/bashball $out/bin/bashball \
              --prefix PATH : ${
                pkgs.lib.makeBinPath (
                  with pkgs;
                  [
                    coreutils
                    util-linux
                    gnutar
                    gnused
                    gnugrep
                    ed
                  ]
                )
              }
          '';
        };

        # the bashball alone: python3, gmsh, ccx and openscad must be on the PATH of whoever runs it
        scadfem = pkgs.stdenvNoCC.mkDerivation {
          pname = "scadfem";
          version = "0.1";
          src = ./.;
          nativeBuildInputs = [ bashball ];
          dontFixup = true; # keep the portable #!/usr/bin/env bash
          buildPhase = ''
            bashball main.sh $(find scadfem -name '*.py') > scadfem.bb
          '';
          installPhase = ''
            install -Dm755 scadfem.bb $out/bin/scadfem
          '';
        };
      in
      {
        packages = {
          inherit bashball scadfem;
          default = scadfem;
        };

        devShell = pkgs.mkShell {
          buildInputs = runtime ++ [ bashball ];
        };
      }
    );
}

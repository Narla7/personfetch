{
  description = "personfetch — fastfetch, but for people";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
        personfetch = pkgs.python3Packages.buildPythonApplication {
          pname = "personfetch";
          version = "0.1.0";
          src = ./.;
          format = "pyproject";
          nativeBuildInputs = [ pkgs.python3Packages.uv-build ];
          propagatedBuildInputs = [ pkgs.python3Packages.pillow ];
          # No test suite yet.
          doCheck = false;
          meta = {
            description = "fastfetch, but for people";
            mainProgram = "personfetch";
          };
        };
      in {
        packages = {
          default = personfetch;
          personfetch = personfetch;
        };
        apps.default = {
          type = "app";
          program = "${personfetch}/bin/personfetch";
        };
        devShells.default = pkgs.mkShell {
          inputsFrom = [ personfetch ];
          packages = [ pkgs.uv pkgs.python3 ];
        };
      });
}

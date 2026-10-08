{
  description = "Ultrasound Storage Design & HDF5 2.x development environment";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    systems.url = "github:nix-systems/default";
  };

  outputs = { self, nixpkgs, systems }:
    let
      eachSystem = nixpkgs.lib.genAttrs (import systems);
    in
    {
      overlays.default = final: prev: rec {
        hdf5_2 = prev.hdf5.overrideAttrs (old: rec {
          version = "2.2.0";
          src = prev.fetchFromGitHub {
            owner = "HDFGroup";
            repo = "hdf5";
            rev = version;
            hash = "sha256-Tp2f8jJjVst0Fd07Wt4+EzjHRRI+8TlD1uWD9sDTw4g=";
          };
          patches = [ ];
          postPatch = (old.postPatch or "") + ''
            for f in src/CMakeLists.txt hl/src/CMakeLists.txt c++/src/CMakeLists.txt hl/c++/src/CMakeLists.txt fortran/src/CMakeLists.txt hl/fortran/src/CMakeLists.txt; do
              if [ -f "$f" ]; then
                substituteInPlace "$f" --replace-warn "\''${exec_prefix}/\''${HDF5_INSTALL_LIB_DIR}" "\''${HDF5_INSTALL_LIB_DIR}"
              fi
            done
          '';
        });

        # Override default hdf5 to 2.x in this scope
        hdf5 = hdf5_2;

        pythonPackagesExtensions = prev.pythonPackagesExtensions ++ [
          (python-final: python-prev: {
            h5py = python-prev.h5py.override {
              hdf5 = hdf5_2;
            };
          })
        ];
      };

      packages = eachSystem (system:
        let
          pkgs = import nixpkgs {
            inherit system;
            overlays = [ self.overlays.default ];
          };
        in
        rec {
          inherit (pkgs) hdf5 hdf5_2;

          # Optional build from the archived local checkout (kept outside the parent Git index)
          hdf5-local = pkgs.hdf5.overrideAttrs (old: {
            src = pkgs.lib.cleanSourceWith {
              src = ./archive/hdf5;
              filter = path: type:
                let base = baseNameOf path; in
                !(type == "directory" && (base == ".git" || base == "build" || base == "result"))
                && !(pkgs.lib.hasSuffix ".o" base || pkgs.lib.hasSuffix ".so" base || pkgs.lib.hasSuffix ".a" base);
            };
          });

          # Compression C libraries
          inherit (pkgs) c-blosc2 zstd lz4;

          python3WithHdf5 = pkgs.python313.withPackages (ps: [
            ps.numpy
            ps.h5py
            ps.hdf5plugin
            ps.blosc2
            ps.zstandard
            ps.lz4
          ]);

          default = hdf5_2;
        }
      );

      devShells = eachSystem (system:
        let
          pkgs = import nixpkgs {
            inherit system;
            overlays = [ self.overlays.default ];
          };
          hdf5Pkg = self.packages.${system}.hdf5_2;
          pythonEnv = self.packages.${system}.python3WithHdf5;
          compressionLibs = [
            pkgs.c-blosc2
            pkgs.zstd
            pkgs.lz4
          ];
        in
        {
          default = pkgs.mkShell {
            name = "ultrasound-hdf5-2-env";
            packages = [
              hdf5Pkg
              hdf5Pkg.bin
              pythonEnv
              pkgs.cmake
              pkgs.ninja
              pkgs.pkg-config
              # CLI compression tools
              pkgs.zstd
              pkgs.lz4
            ] ++ compressionLibs;

            HDF5_DIR = "${hdf5Pkg}";
            HDF5_VERSION = "2.2.0";

            PKG_CONFIG_PATH = pkgs.lib.makeSearchPathOutput "dev" "lib/pkgconfig" ([ hdf5Pkg ] ++ compressionLibs);
            CPATH = pkgs.lib.makeSearchPathOutput "dev" "include" ([ hdf5Pkg ] ++ compressionLibs);
            LIBRARY_PATH = pkgs.lib.makeLibraryPath ([ hdf5Pkg ] ++ compressionLibs);

            shellHook = ''
              echo "================================================================"
              echo "  UltrasoundStorageDesign Development Shell (HDF5 2.x & Codecs) "
              echo "================================================================"
              echo "  - HDF5 C/C++ library: 2.2.0 (HDF5_DIR=$HDF5_DIR)"
              echo "  - CLI Tools: h5dump, h5ls, h5diff, zstd, lz4"
              echo "  - C Libraries: c-blosc2, libzstd, liblz4"
              echo "  - Python 3.13: h5py $(python3 -c 'import h5py; print(h5py.__version__, "(HDF5 " + h5py.version.hdf5_version + ")")' 2>/dev/null || true)"
              echo "                 hdf5plugin, blosc2, zstandard, lz4, numpy"
              echo "================================================================"
            '';
          };
        }
      );
    };
}

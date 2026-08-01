cmake_minimum_required(VERSION 3.13.4)

project(DentoFac)

#-----------------------------------------------------------------------------
# Extension metadata
set(EXTENSION_HOMEPAGE "https://github.com/DentoFac/SlicerDentoFac")
set(EXTENSION_CATEGORY "Dentistry")
set(EXTENSION_CONTRIBUTORS "DentoFac contributors; Gauthier DOT (upstream DentalSegmentator)")
set(EXTENSION_DESCRIPTION
  "A curated, integrated set of dento-maxillo-facial workflows for 3D Slicer, including AI dental CT and CBCT segmentation.")
set(EXTENSION_DEPENDS "NNUNet")

# The NNUNet extension is an external runtime dependency.  A developer build
# may not have its CMake package available, while its installed scripted-module
# directory is sufficient for the Segmentator generic module test.  Keep this
# opt-in path test-only; it is never packaged or used at runtime.
set(DENTOFAC_TEST_NNUNET_MODULE_PATH "" CACHE PATH
  "Directory containing SlicerNNUNet.py for DentoFac CTest")

#-----------------------------------------------------------------------------
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

# The Hub is added first because its scripted-module install rules package
# DentoFacLib for workflow modules such as DentoFacSegmentator.
add_subdirectory(DentoFac)
add_subdirectory(Segmentation)

# Release packages retain their license, notices, and user-facing readme next
# to the extension metadata. Model weights and excluded test data are never
# installed by these rules.
install(FILES LICENSE THIRD_PARTY_NOTICES.md README.md
  DESTINATION ${Slicer_INSTALL_SHARE_DIR}/DentoFac)
install(DIRECTORY LICENSES/
  DESTINATION ${Slicer_INSTALL_SHARE_DIR}/DentoFac/LICENSES)

#-----------------------------------------------------------------------------
include(${Slicer_EXTENSION_GENERATE_CONFIG})
include(${Slicer_EXTENSION_CPACK})

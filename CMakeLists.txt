cmake_minimum_required(VERSION 3.13.4)

project(DentoFac)

#-----------------------------------------------------------------------------
# Extension metadata
set(EXTENSION_HOMEPAGE "https://github.com/DentoFac/SlicerDentoFac")
set(EXTENSION_CATEGORY "Dentistry")
set(EXTENSION_CONTRIBUTORS "DentoFac contributors")
set(EXTENSION_DESCRIPTION
  "A curated, integrated set of dento-maxillo-facial workflows for 3D Slicer.")
set(EXTENSION_DEPENDS "NA")

#-----------------------------------------------------------------------------
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

# The Hub is added first because its scripted-module install rules package
# DentoFacLib for workflow modules such as DentoFacSegmentator.
add_subdirectory(DentoFac)
add_subdirectory(Segmentation)

#-----------------------------------------------------------------------------
include(${Slicer_EXTENSION_GENERATE_CONFIG})
include(${Slicer_EXTENSION_CPACK})

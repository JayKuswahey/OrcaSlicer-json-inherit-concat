#!/usr/bin/env bash

## this script requires the tool jq to be installed on your machine, and available in ${PATH}

## Create a function to display timestamps when you echo something.
## Timestamp is year/month/day to make stuff sort correctly if ever need be
function echodate(){
  echo $(date "+%Y%m%d-%H%M%S") "${@}"
}

## Create a function to get the "inherits" JSON key, except when it's empty
## The 'select' statement is to remove the 'null' value jq delivers by default
## We actually want nonthing-nothing, a void.
function jqinherit(){
  jq -r '.inherits | select( . != null )' "${1}"
}

function usage(){
  dqt='"'
  echo ""
  echo "Usage: ${0} -f <fileToCheck> -c <componentName> -l <orcaProfilesLocation> -t <targetLocation> -d <true>" 1>&2
  echo ""
  echo "Example: ${0} -f ${dqt}Sunlu Pla +${dqt} -c process -l ${dqt}/home/jaykay/.config/orca${dqt} -t ${dqt}/opt/hereIsWhereIwantIt${dqt} -d true" 1>&2
  echo ""
  echo "Be sure to quote your files and paths, especially when there's spaces in it."
  echo "To not debug, just remove -d completely, don't set it to false."
  exit ${1}
}

# Initialize parameters specified from command line
while getopts ":f:c:d:t:l:" arg; do
  case "${arg}" in
    f)
      fileToCheck=${OPTARG}
      filenameWithExtension="${fileToCheck##*/}"
      targetFileSource="$(echo ${filenameWithExtension%.*} | tr -d '[:space:][:punct:]')"
      ;;
    c)
      componentName=${OPTARG}
      ;;
    l)
      orcaProfilesLocation=${OPTARG}
      ;;
    t)
      targetLocation=${OPTARG}
      ;;
    d)
      DEBUG="true"
      ;;
  esac
done
shift $((OPTIND-1))

## Stop altogether if there's no parameters
if [[ -z ${fileToCheck} ]] ; then
    echodate "No filename given, quitting."
    usage 10
fi

if [[ -z ${componentName} ]] ; then
    echodate "No component given, quitting."
    usage 11
fi

## Set global variables, populate targetLocation if it's not given
[[ ${DEBUG} ]] && echodate "Setting up global variables"
bashBaseDir='.'
[[ ${targetLocation} ]] || targetLocation="/tmp"
targetFile="${targetLocation}/orcaslicer_${componentName}_${targetFileSource}_inherit_concat-$(date "+%Y%m%d-%H%M%S").json"
## orcaProfilesLocation is set up for MacOS, populate if not given, Linux will require a different default path
[[ ${orcaProfilesLocation} ]] || orcaProfilesLocation="/Users/$(whoami)/Library/Application Support/OrcaSlicer/system/BBL/${componentName}"

## Create a new array to populate lateron
[[ ${DEBUG} ]] && echodate "Setting up variable arrays"
declare -a dependencyArray
declare -a dependencyReverse

## Add our first parameter into the array
dependencyArray+=( "${fileToCheck}" )

## Retrieve the settings file we're depending on, or better, where we interit from
ancestorFile=$(jqinherit "${fileToCheck}")
if [[ ! -z "${ancestorFile}" ]] ; then
  echodate "We have a dependency, building tree."
  ## Enter a loop, while we keep finding 'inherits' in the JSON, we keep going
  while [[ -n "${ancestorFile}" ]] ; do
    ## create a temporary variable
    checkFile="${bashBaseDir}/${ancestorFile}.json"
    [[ ${DEBUG} ]] && echodate "Checking ${checkFile}"
    ## Check if the file exists on the machine
    if [[ -f "${checkFile}" ]] ; then
      [[ ${DEBUG} ]] && echodate "File ${checkFile} found, adding to tree."
      ## It does exist, so add to the list of dependencies
      dependencyArray+=( "${checkFile}" )
      [[ ${DEBUG} ]] && "File ${checkFile} added, checking more inheritance"
      ## delete the variable so to speak, so it won't accidentally bleed into the next loop
      unset ancestorFile
      ## Check inside the new file if there's another dependency
      ancestorFile=$(jqinherit "${checkFile}")
    else
      ## The file does not exist in current directory, so check OrcaSlicer defaults
      checkFile="${orcaProfilesLocation}/${ancestorFile}.json"
      [[ ${DEBUG} ]] && echodate "File not found, checking ${checkFile} now."
      ## Check if the file exists on the machine
      if [[ ! -f "${checkFile}" ]] ; then
        ## We found a dependency, but we cannot locate the file...
        [[ ${DEBUG} ]] && echodate "File ${checkFile} not found either, quitting."
        exit 20
      else
        [[ ${DEBUG} ]] && echodate "File ${checkFile} found, adding to tree."
        ## It does exist, so add to the list of dependencies
        dependencyArray+=( "${checkFile}" )
        [[ ${DEBUG} ]] && echodate "File ${checkFile} added, checking further inheritance"
        ## delete the variable so to speak, so it won't accidentally bleed into the next loop
        unset ancestorFile
        ## Check inside the new file if there's another dependency
        ancestorFile=$(jqinherit "${checkFile}")
      fi
    fi
  done
  [[ ${DEBUG} ]] && echodate "No further inheritance found."
else
  ## The result was empty, so we quite
  echodate "There is no dependency in this file, quitting."
  exit 12
fi

## Showcase our work
[[ ${DEBUG} ]] && echodate "We now have the following array which needs to be reversed:"
[[ ${DEBUG} ]] && echodate "${dependencyArray[@]}"

## actually reverse the array
for (( i=${#dependencyArray[@]}-1; i>=0; i-- )) ; do
  dependencyReverse+=( "${dependencyArray[i]}" )
done

## Showcase the result
[[ ${DEBUG} ]] && echodate "Done! We now have the following reversed array:"
[[ ${DEBUG} ]] && echodate "${dependencyReverse[@]}"

## use jq to overlap all JSON files, remove the inherits key (there are no inherits anymore)
## and sort the result in alphabetical order into a unique enough file with a timestamp
[[ ${DEBUG} ]] && echodate "Let's build a full profile!"
jq -s 'add | del(.inherits) | with_entries(.key |= ascii_downcase) | to_entries | sort_by(.key) | from_entries' "${dependencyReverse[@]}" > "${targetFile}"

## if exit-code of jq merge/add is 0 then success, else failure
if [[ $? -eq 0 ]] ; then
  echodate "Done! Cleaning up after myself!"
  ## Unset all variables to make sure they don't "bleed over" into other stuff
  unset dependencyReverse dependencyArray checkFile ancestorFile bashBaseDir orcaProfilesLocation fileToCheck filenameWithExtension targetFileSource componentName orcaProfilesLocation targetLocation DEBUG
  ## if exit-code of unset is 0 then success, else failure
  if [[ $? -eq 0 ]] ; then
    echodate "Cleanup successful!"
    echodate "Please check your result in file ${targetFile}"
    unset targetFile
  else
    echodate "Cleanup failed!"
    exit $?
  fi
else
  echodate "jq failed to execute, check deeper..."
  exit $?
fi

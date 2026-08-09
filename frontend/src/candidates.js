import candidateDataset from '../../backend/app/data/candidates.json'

export const allCandidates = candidateDataset.candidates
export const candidateOptions = allCandidates.slice(0, 5)

export function getCandidateMilestoneCount(candidate) {
  return candidate.missions.length
}

export function getCandidateMeta(candidate) {
  return `${candidate.member.yearsExperience} years · ${candidate.member.education}`
}

export function getCandidateHighlights(candidate, limit = 3) {
  return candidate.missions.slice(0, limit).map((mission) => mission.title)
}
import { handleMultiplayerRequest } from './multiplayer-core.js'

export default async function handler(req, res) {
  await handleMultiplayerRequest(req, res)
}

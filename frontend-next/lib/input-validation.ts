const EMOJI_PATTERN = /[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{200D}\u{FE0F}]/u;

export function containsEmoji(value: string): boolean {
  return EMOJI_PATTERN.test(value);
}

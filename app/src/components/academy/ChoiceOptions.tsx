import { Check, X } from 'lucide-react'

export function ChoiceOptions({
  options,
  multiple,
  picked,
  revealed,
  submitting,
  correctOptions,
  onPick,
  onCheck,
}: {
  options: string[]
  multiple: boolean
  picked: number[]
  revealed: boolean
  submitting: boolean
  correctOptions: string[]
  onPick: (index: number) => void
  onCheck?: () => void
}) {
  const pickedSet = new Set(picked)
  const correctSet = new Set(correctOptions)
  return (
    <>
      <div className="quiz__options" role={multiple ? 'group' : undefined} aria-label={multiple ? 'Choose all that apply' : undefined}>
        {options.map((option, optionIndex) => {
          const pickedThis = pickedSet.has(optionIndex)
          const showCorrect = revealed && correctSet.has(option)
          const showWrong = revealed && pickedThis && !correctSet.has(option)
          let cls = 'quiz__option'
          if (showCorrect) cls += ' is-correct'
          else if (showWrong) cls += ' is-wrong'
          else if (!revealed && multiple && pickedThis) cls += ' is-picked'
          return (
            <button
              key={optionIndex}
              type="button"
              className={cls}
              aria-pressed={multiple ? pickedThis : undefined}
              disabled={revealed || submitting}
              onClick={() => onPick(optionIndex)}
            >
              <span className="quiz__option-text">{option}</span>
              {showCorrect ? (
                <span className="quiz__option-status">
                  <Check size={16} /> Correct
                </span>
              ) : null}
              {showWrong ? (
                <span className="quiz__option-status">
                  <X size={16} /> Incorrect
                </span>
              ) : null}
            </button>
          )
        })}
      </div>
      {multiple && !revealed ? (
        <div className="quiz__check">
          <button type="button" className="study__btn" disabled={submitting || picked.length === 0} onClick={onCheck}>
            <Check size={16} /> {submitting ? 'Checking…' : 'Check answer'}
          </button>
        </div>
      ) : null}
    </>
  )
}

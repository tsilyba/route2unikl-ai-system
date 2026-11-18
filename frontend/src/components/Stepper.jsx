import React from 'react';

const DEFAULT_STEPS = [
  'Interest',
  'Upload Results',
  'AI Assessment',
  'Recommendation',
  'Preparation Plan'
];

const Stepper = ({ currentStep = 1, steps = DEFAULT_STEPS }) => {
  return (
    <div className="flex justify-between items-center mb-12 border-b pb-8">
      {steps.map((step, idx) => {
        const stepNum = idx + 1;
        const isCompleted = stepNum < currentStep;
        const isCurrent = stepNum === currentStep;

        return (
          <div key={idx} className="flex flex-col items-center flex-1 relative">
            {/* Step Circle */}
            <div
              className={`w-10 h-10 rounded-full flex items-center justify-center font-bold mb-2 z-10 transition-all ${
                isCompleted
                  ? 'bg-blue-600 text-white shadow-md'
                  : isCurrent
                  ? 'bg-blue-600 text-white shadow-md ring-4 ring-blue-100'
                  : 'bg-gray-100 text-gray-400'
              }`}
            >
              {isCompleted ? '✓' : stepNum}
            </div>

            {/* Step Label */}
            <span
              className={`text-xs font-bold text-center px-1 ${
                isCurrent || isCompleted ? 'text-blue-600' : 'text-gray-400'
              }`}
            >
              {step}
            </span>

            {/* Connecting Line to next step */}
            {idx < steps.length - 1 && (
              <div
                className={`absolute top-5 left-1/2 w-full h-[2px] -z-0 transition-all ${
                  stepNum < currentStep ? 'bg-blue-600' : 'bg-gray-200'
                }`}
              />
            )}
          </div>
        );
      })}
    </div>
  );
};

export default Stepper;
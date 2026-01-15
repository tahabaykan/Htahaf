import React from 'react'
import toast from 'react-hot-toast'

const GROUP_FILES = [
  'janek_ssfinekheldcilizyeniyedi.csv',
  'janek_ssfinekheldcommonsuz.csv',
  'janek_ssfinekhelddeznff.csv',
  'janek_ssfinekheldff.csv',
  'janek_ssfinekheldflr.csv',
  'janek_ssfinekheldgarabetaltiyedi.csv',
  'janek_ssfinekheldkuponlu.csv',
  'janek_ssfinekheldkuponlukreciliz.csv',
  'janek_ssfinekheldkuponlukreorta.csv',
  'janek_ssfinekheldnff.csv',
  'janek_ssfinekheldotelremorta.csv',
  'janek_ssfinekheldsolidbig.csv',
  'janek_ssfinekheldtitrekhc.csv',
  'janek_ssfinekhighmatur.csv',
  'janek_ssfineknotbesmaturlu.csv',
  'janek_ssfineknotcefilliquid.csv',
  'janek_ssfineknottitrekhc.csv',
  'janek_ssfinekrumoreddanger.csv',
  'janek_ssfineksalakilliquid.csv',
  'janek_ssfinekshitremhc.csv'
]

const GroupButtons = ({ onLoadGroup }) => {
  const handleGroupClick = (filename) => {
    if (onLoadGroup) {
      onLoadGroup(filename)
    }
  }

  const getShortName = (filename) => {
    return filename.replace('janek_ssfinek', '').replace('.csv', '')
  }

  return (
    <div className="bg-white rounded-lg shadow p-4 mb-4">
      <h3 className="text-sm font-medium text-gray-700 mb-3">Grup Dosyaları</h3>
      <div className="flex flex-wrap gap-2">
        {GROUP_FILES.map((file, index) => (
          <button
            key={index}
            onClick={() => handleGroupClick(file)}
            className="px-3 py-1.5 text-xs font-medium text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200 transition-colors"
          >
            {getShortName(file)}
          </button>
        ))}
      </div>
    </div>
  )
}

export default GroupButtons










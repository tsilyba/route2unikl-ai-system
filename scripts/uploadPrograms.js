const admin = require('firebase-admin');
const fs = require('fs');
const csv = require('csv-parser');
const path = require('path');

// Initialize Firebase Admin SDK with your service account credentials
admin.initializeApp({
    credential: admin.credential.cert(require(path.join('C:', 'Users', 'user', 'Downloads', 'route2unikl-firebase-adminsdk-fbsvc-da1213ea26.json'))),
    databaseURL: "https://your-project-id.firebaseio.com"  // Add your project URL here
});

// Get a reference to Firestore
const db = admin.firestore();

// Path to your CSV file
const csvFilePath = './unikl_programmes.csv';

// Function to upload CSV data to Firestore
const uploadProgramsToFirestore = async () => {
  const programs = [];

  // Read CSV file
  fs.createReadStream(csvFilePath)
    .pipe(csv())
    .on('data', (row) => {
      // Check if required fields are not empty or undefined
      if (row.title && row.level && row.campuses && row.short_description && row.specialisation && row.link) {
        programs.push({
          title: row.title,
          level: row.level,
          campuses: row.campuses,
          short_description: row.short_description,
          specialisation: row.specialisation,
          link: row.link
        });
      } else {
        // Log rows with missing values
        console.log(`Skipping row with missing data: ${JSON.stringify(row)}`);
      }
    })
    .on('end', async () => {
      console.log('CSV file successfully processed.');

      // Loop through each program and upload to Firestore
      for (const program of programs) {
        try {
          // Ensure all fields are valid before uploading
          await db.collection('programs').add({
            title: program.title,
            level: program.level,
            campuses: program.campuses,
            short_description: program.short_description,
            specialisation: program.specialisation,
            link: program.link,
          });
        } catch (error) {
          console.error(`Error adding program: ${program.title} - ${error.message}`);
        }
      }

      console.log('Programs uploaded to Firestore successfully!');
    });
};

// Run the function to upload the programs
uploadProgramsToFirestore();
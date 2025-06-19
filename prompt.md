prompt.txt
Endeavor FDE Takehome Technical
Maximum time: 2.5 hours
I. Introduction
One of Endeavor’s core products is automating document processing for our customers’ most critical business processes – sales order entry.

Goal: Build an MVP of an automated document processing application for manufacturing trade documents. Take in documents, extract the content, structure it, and write it back to a database.

Context: Here’s a video showing you how an employee at one of our clients might perform this task manually today. Our goal is to automate this task as fully as possible: Example of app

Data: Download example purchase orders and the product catalog: Example POs and product catalog

Video Explanation: https://www.loom.com/share/c347f7c61f67464288aed0fdc18ec5b3?sid=85f105e7-ff46-42c0-a9ba-6ecc3d014e37

Human Process Today:
Here’s how people would perform this task today:
Receive trade document (e.g. invoice or purchase order) via email
Open it up and scan it
Match each line item in the document to the product in their manufacturing product catalog that is most likely to be that line item
Enter this information into a database table

Your Solution Requirements (High Level):
Hopefully you have intuition on what the ideal solution looks like. Here’s what it could look like:
Upload a PDF to a web application
Parse PDF in some manner to extract relevant information (The line items)
Match each extracted line item to most similar products in the product catalog
Give a human user the option to adjust the matchings
On confirmation, write back this information somewhere (Being able to download a csv of matchings is fine for the base implementation)
Write a README with instructions on how to run your implementation
Create a ~1min screen recording video demonstrating the functionality of your solution. We recommend using Loom. Please add the video link to your README and to your reply to the email that delivered this assignment to you..(This can be done after the 2.5 hr window)

This is a very high level description, and there will be opportunities to improve each step of the process. This can all be implemented with only a frontend, however a good solution will have a frontend (vite, next, etc), python backend (flask, fastapi, etc), and database (postgres, sql, firebase, etc).

For simplicity, we have provided you an API to call to perform Step 2 and 3 (matching each line item to the most similar product). In production, this involves using language models and a host of other search techniques to get to high accuracy.
Step 2 Extraction endpoint: 
Link to extraction endpoint
Note: don’t change the document names, the extraction endpoint is hardcoded for interview purposes . The document names for extraction should be:
Easy - 1.pdf, Easy - 2.pdf, Easy - 3.pdf, Medium - 1.pdf, Medium - 2.pdf, Medium - 3.pdf, Hard - 1.pdf, Hard - 2.pdf, “Hard -3.pdf”
Step 3 Matching endpoint: 
Link to matching endpoint
As a bonus, implement your own matching function to match purchase order item descriptions to items in the product catalog (unique_fastener_catalog.csv). This should be the last priority as the ‘completeness’ evaluation requires everything except for this.

The purpose of this interview is to test you on your ability to quickly build an application for a hypothetical customer. You are allowed to use anything at your disposal, including AI tools for code generation.

II. Submission Instructions
Failure to follow these instructions will result in a failing grade

Before the 2.5 hr window is over
Create a private GitHub repository
Share it with (ryan-endeavor) by adding them as a collaborator.

After the 2.5 hr window is over
Create a ~1 minute demo video (no audio required) walking through the functionality of your app. We recommend either using Loom, uploading the video to YouTube, or uploading it to Google Drive. Loom is the easiest.
Add the link to this video to your README
Submit this submission form.

III. Evaluating Your Solution
We rank solutions with a point-based system. See how many points you can accumulate!

We do not expect you to do everything here (although you’re free to try it) — pick specific areas you are interested in so that you can showcase your skillset. There’s a variety of areas to flesh out from the base solution.

Completeness: MAX +50 points
Level
Points
Some requirement missing (1, 2, 3, 4, 5, or 6)
0
All requirements met, without the custom matching bonus. Includes frontend, backend, and database. (1, 2, 3, 4, 5, and 6)
50



Human-in-the-Loop Verification: MAX +25 points
Level
Points
Basic verification via selection from dropdown menu (required)
0
Additional functionality:
Allowing users to search for specific line items from the product catalog (for cases where the top 10 doesn’t include the correct item)
Allowing users to alter the line items extracted to add/edit/remove items
User changes are stored persistently on the backend
Up to 25 points


Frontend: MAX +50 points
Level
Points
Meets requirements
0
Elegant user experience and/or design
Up to 50 points


Architecture (backend): MAX +50 points
Level
Points
Stateless Architecture
0
Stateful Architecture (e.g. queues, database, displaying a dashboard with the confirmed matchings)
Up to 50 points
Custom Matching (bonus)
Up to 50 points


Rubric
Area
MAX POINTS
Your Score
Completeness
50


Human-in-the-Loop
25


Frontend
50


Architecture
100


If repo is not private OR
No demo video provided within 30 mins of completion
- 225


TOTAL
225





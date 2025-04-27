# SmartInfo Web Frontend

This is the web frontend for the SmartInfo application, built with React, Next.js, and Ant Design. It communicates with the FastAPI backend to provide a modern, accessible user interface for the SmartInfo information analysis tool.

## Features

- News management (browsing, filtering, searching, viewing details)
- Intelligent news analysis display
- Question-answering system with chat history
- Settings management for the application

## Technologies Used

- **React**: UI component library
- **Next.js**: React framework for server-side rendering and routing
- **Ant Design**: UI component framework
- **Axios**: HTTP client for API communication
- **TypeScript**: Type-safe JavaScript

## Getting Started

### Prerequisites

- Node.js (v14 or later recommended)
- npm or yarn
- Backend API server running (default at http://localhost:8000)

### Installation

1. Clone the repository
2. Navigate to the frontend directory:
   ```
   cd frontend
   ```

3. Install dependencies:
   ```
   npm install
   # or
   yarn install
   ```

4. Set up environment variables (optional):
   Create a `.env.local` file in the frontend directory and add:
   ```
   NEXT_PUBLIC_API_URL=http://localhost:8000
   ```
   (Adjust the URL if your backend is hosted elsewhere)

### Running the Application

1. Start the development server:
   ```
   npm run dev
   # or
   yarn dev
   ```

2. Open [http://localhost:3000](http://localhost:3000) in your browser to see the application.

### Testing the Application

The application includes a test suite using Jest and React Testing Library.

1. Run the tests:
   ```
   npm test
   # or
   yarn test
   ```

2. Run tests with coverage report:
   ```
   npm test -- --coverage
   # or
   yarn test --coverage
   ```

3. Test backend connectivity:
   ```
   npm run test:backend
   # or
   yarn test:backend
   ```
   This will test all major API endpoints to ensure connectivity with the backend.

4. Testing against the backend:
   - Make sure the backend API is running at the URL specified in your `.env.local` file
   - Navigate through the application to test features:
     - Fetch news from sources
     - Filter and search news
     - View news details
     - Analyze news
     - Chat with the application
     - Configure settings

### Building for Production

To create a production build:

```
npm run build
# or
yarn build
```

## Project Structure

- `src/pages/`: Next.js pages
- `src/components/`: React components
- `src/services/`: API services for backend communication
- `src/utils/`: Utility functions and types
- `src/styles/`: Global and component-specific styles
- `src/__tests__/`: Test files for components and pages

## Backend Integration

This frontend is designed to work with the SmartInfo FastAPI backend. Make sure the backend is running before using the frontend. The backend provides RESTful APIs for all the functionalities required by the frontend.

## License

This project is licensed under the same terms as the main SmartInfo application. 